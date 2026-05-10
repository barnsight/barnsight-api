"""Edge device ingestion routes authenticated with X-BarnSight-Key."""

import base64
import binascii
import json
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from api.auth_dependencies import require_edge_scope
from api.dependencies import get_mongo_client, get_redis_client, limit_dependency
from core.config import settings
from core.database import MongoClient, RedisClient
from core.schemas.devices import DeviceConfig, DeviceHeartbeat
from core.schemas.events import EventCreate
from core.services.cloudinary_service import upload_base64_image
from crud.event_crud import EventCRUD
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

router = APIRouter(tags=["Edge"])


class EdgeEventResult(BaseModel):
  event_id: str
  status: str = "created"
  account_id: str
  farm_id: str
  barn_id: Optional[str] = None
  device_id: Optional[str] = None


class EdgeEventCreate(EventCreate):
  device_id: Optional[str] = Field(None, description="Resolved from API key when assigned")


class EdgeSnapshotUpload(BaseModel):
  model_config = ConfigDict(extra="forbid")

  camera_id: str
  event_id: Optional[str] = None
  image_snapshot: str = Field(..., description="Base64 image/jpeg, image/png, or image/webp")
  content_type: str = Field("image/jpeg", pattern=r"^image/(jpeg|png|webp)$")
  captured_at: Optional[datetime] = None

  @field_validator("image_snapshot")
  @classmethod
  def validate_snapshot_size(cls, value: str) -> str:
    payload = value
    if payload.lower().startswith("data:"):
      header = payload.lower().split(",", 1)[0]
      if header not in {
        "data:image/jpeg;base64",
        "data:image/png;base64",
        "data:image/webp;base64",
      }:
        raise ValueError("image_snapshot must be image/jpeg, image/png, or image/webp")
      payload = payload.split(",", 1)[1]
    try:
      decoded_size = len(base64.b64decode(payload, validate=True))
    except (binascii.Error, ValueError) as exc:
      raise ValueError("image_snapshot must be valid base64") from exc
    if decoded_size > settings.EDGE_MAX_SNAPSHOT_BYTES:
      raise ValueError(
        f"image_snapshot exceeds max decoded size of {settings.EDGE_MAX_SNAPSHOT_BYTES} bytes"
      )
    return value


class EdgeCameraSyncItem(BaseModel):
  model_config = ConfigDict(extra="forbid")

  camera_id: str
  barn_id: Optional[str] = None
  name: Optional[str] = None
  stream_label: Optional[str] = None
  status: str = "online"
  zones: list[dict[str, Any]] = Field(default_factory=list)


class EdgeCameraSync(BaseModel):
  model_config = ConfigDict(extra="forbid")

  device_id: Optional[str] = None
  cameras: list[EdgeCameraSyncItem]


def _now() -> datetime:
  return datetime.now(timezone.utc)


def _edge_ids(key_doc: dict) -> dict[str, Optional[str]]:
  account_id = key_doc.get("account_id") or key_doc.get("owner_id")
  farm_id = key_doc.get("farm_id") or account_id
  return {
    "account_id": account_id,
    "farm_id": farm_id,
    "barn_id": key_doc.get("barn_id"),
    "device_id": key_doc.get("device_id"),
  }


async def _audit(db, action: str, payload: dict) -> None:
  await db["audit_logs"].insert_one({"action": action, "created_at": _now(), **payload})


async def _camera_for_event(db, ids: dict, event: EdgeEventCreate) -> Optional[dict]:
  camera = await db["cameras"].find_one(
    {"account_id": ids["account_id"], "camera_id": event.camera_id}
  )
  if not camera:
    return None
  if ids.get("device_id") and camera.get("device_id") != ids["device_id"]:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Camera is not linked to this API key device",
    )
  if ids.get("barn_id") and camera.get("barn_id") != ids["barn_id"]:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Camera is not linked to this API key barn",
    )
  return camera


async def _validate_zone(db, ids: dict, camera_id: str, zone_id: Optional[str]) -> None:
  if not zone_id:
    return
  zone = await db["detection_zones"].find_one(
    {"account_id": ids["account_id"], "camera_id": camera_id, "zone_id": zone_id}
  )
  if not zone:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST, detail="zone_id does not belong to camera"
    )


async def _store_event(
  event: EdgeEventCreate,
  key_doc: dict,
  mongo: MongoClient,
  redis: RedisClient,
  background_tasks: BackgroundTasks,
) -> dict:
  db = mongo.get_database("barnsight")
  ids = _edge_ids(key_doc)
  if not ids["account_id"]:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED, detail="API key is missing account scope"
    )

  camera = await _camera_for_event(db, ids, event)
  await _validate_zone(db, ids, event.camera_id, event.zone_id)

  event_dict = event.model_dump()
  event_dict.update(
    {
      "account_id": ids["account_id"],
      "farm_id": ids["farm_id"],
      "barn_id": ids["barn_id"] or (camera or {}).get("barn_id") or event.barn_id,
      "device_id": ids["device_id"] or (camera or {}).get("device_id") or event.device_id,
      "ingested_at": _now(),
      "api_key_prefix": key_doc.get("prefix"),
    }
  )

  if event.image_snapshot:
    folder = f"barnsight/events/{ids['account_id']}"
    event_dict["image_snapshot"] = await upload_base64_image(event.image_snapshot, folder=folder)

  result = await EventCRUD(db).create_event(event_dict)
  await _audit(
    db,
    "edge.event_ingested",
    {
      "account_id": ids["account_id"],
      "farm_id": ids["farm_id"],
      "barn_id": event_dict.get("barn_id"),
      "device_id": event_dict.get("device_id"),
      "camera_id": event.camera_id,
      "event_object_id": result.get("_id"),
    },
  )
  await redis.publish(f"account:{ids['account_id']}:events", json.dumps(result, default=str))
  if result.get("confidence", 0) > 0.8:
    from core.services.alert_service import check_and_send_alert

    background_tasks.add_task(check_and_send_alert, ids["account_id"], result)
  return result


@router.post(
  "/heartbeat", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def edge_heartbeat(
  heartbeat: DeviceHeartbeat,
  key_doc: Annotated[dict, Depends(require_edge_scope("edge:heartbeat"))],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  ids = _edge_ids(key_doc)
  device_id = ids.get("device_id") or heartbeat.device_id
  barn_id = ids.get("barn_id") or heartbeat.barn_id or "unknown"
  db = mongo.get_database("barnsight")
  now = _now()
  heartbeat_data = heartbeat.model_dump(exclude_none=True)
  heartbeat_data.update(
    {
      "account_id": ids["account_id"],
      "farm_id": ids["farm_id"],
      "device_id": device_id,
      "barn_id": barn_id,
      "last_seen_at": now,
      "updated_at": now,
    }
  )
  await db["devices"].update_one(
    {"account_id": ids["account_id"], "device_id": device_id},
    {
      "$set": {**heartbeat_data, "status": heartbeat.status},
      "$setOnInsert": {"created_at": now, "name": device_id},
    },
    upsert=True,
  )
  await db["cameras"].update_one(
    {"account_id": ids["account_id"], "camera_id": heartbeat.camera_id},
    {
      "$set": heartbeat_data,
      "$setOnInsert": {"created_at": now, "name": heartbeat.camera_id},
    },
    upsert=True,
  )
  await redis.setex(
    f"camera:{ids['account_id']}:{heartbeat.camera_id}:status",
    settings.DEVICE_HEARTBEAT_TTL_SECONDS,
    heartbeat.status,
  )
  await redis.setex(
    f"device:{ids['account_id']}:{device_id}:status",
    settings.DEVICE_HEARTBEAT_TTL_SECONDS,
    heartbeat.status,
  )
  return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
  "/events",
  response_model=EdgeEventResult,
  status_code=status.HTTP_201_CREATED,
  dependencies=[Depends(limit_dependency)],
)
async def edge_create_event(
  event: EdgeEventCreate,
  key_doc: Annotated[dict, Depends(require_edge_scope("edge:event:create"))],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
  background_tasks: BackgroundTasks,
):
  result = await _store_event(event, key_doc, mongo, redis, background_tasks)
  ids = _edge_ids(key_doc)
  return {
    "event_id": result.get("_id"),
    "status": "created",
    "account_id": ids["account_id"],
    "farm_id": ids["farm_id"],
    "barn_id": result.get("barn_id"),
    "device_id": result.get("device_id"),
  }


@router.post(
  "/events/bulk",
  response_model=list[EdgeEventResult],
  status_code=status.HTTP_201_CREATED,
  dependencies=[Depends(limit_dependency)],
)
async def edge_create_events_bulk(
  events: list[EdgeEventCreate],
  key_doc: Annotated[dict, Depends(require_edge_scope("edge:event:create"))],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
  background_tasks: BackgroundTasks,
):
  results = []
  ids = _edge_ids(key_doc)
  for event in events:
    stored = await _store_event(event, key_doc, mongo, redis, background_tasks)
    results.append(
      {
        "event_id": stored.get("_id"),
        "status": "created",
        "account_id": ids["account_id"],
        "farm_id": ids["farm_id"],
        "barn_id": stored.get("barn_id"),
        "device_id": stored.get("device_id"),
      }
    )
  return results


@router.post("/snapshots", dependencies=[Depends(limit_dependency)])
async def edge_upload_snapshot(
  snapshot: EdgeSnapshotUpload,
  key_doc: Annotated[dict, Depends(require_edge_scope("edge:snapshot:upload"))],
):
  ids = _edge_ids(key_doc)
  folder = f"barnsight/snapshots/{ids['account_id']}"
  url = await upload_base64_image(snapshot.image_snapshot, folder=folder)
  return {"snapshot_url": url, "account_id": ids["account_id"], "farm_id": ids["farm_id"]}


@router.get("/config", dependencies=[Depends(limit_dependency)])
async def edge_get_config(
  key_doc: Annotated[dict, Depends(require_edge_scope("edge:device:config:read"))],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  ids = _edge_ids(key_doc)
  if not ids.get("device_id"):
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST, detail="API key is not assigned to a device"
    )
  db = mongo.get_database("barnsight")
  config = await db["device_configs"].find_one(
    {"account_id": ids["account_id"], "device_id": ids["device_id"]}
  )
  if not config:
    config = DeviceConfig().model_dump()
    config.update(
      {"account_id": ids["account_id"], "device_id": ids["device_id"], "updated_at": _now()}
    )
  if config.get("_id") is not None:
    config["_id"] = str(config["_id"])
  return config


@router.post("/cameras/sync", dependencies=[Depends(limit_dependency)])
async def edge_sync_cameras(
  sync: EdgeCameraSync,
  key_doc: Annotated[dict, Depends(require_edge_scope("edge:camera:sync"))],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  ids = _edge_ids(key_doc)
  device_id = ids.get("device_id") or sync.device_id
  if not device_id:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="device_id is required")
  db = mongo.get_database("barnsight")
  now = _now()
  for camera in sync.cameras:
    barn_id = ids.get("barn_id") or camera.barn_id or "unknown"
    await db["cameras"].update_one(
      {"account_id": ids["account_id"], "camera_id": camera.camera_id},
      {
        "$set": {
          "account_id": ids["account_id"],
          "farm_id": ids["farm_id"],
          "barn_id": barn_id,
          "device_id": device_id,
          "name": camera.name or camera.camera_id,
          "stream_label": camera.stream_label,
          "status": camera.status,
          "last_seen_at": now,
          "updated_at": now,
        },
        "$setOnInsert": {"created_at": now},
      },
      upsert=True,
    )
  return {
    "status": "synced",
    "count": len(sync.cameras),
    "account_id": ids["account_id"],
    "farm_id": ids["farm_id"],
  }

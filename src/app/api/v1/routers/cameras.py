"""Camera query, status, zones, and detection routes."""

from typing import Annotated

from api.dependencies import get_mongo_client, limit_dependency
from api.v1.routers.devices import _camera_online, _now, _serialize_id, get_device_owner
from core.config import settings
from core.database import MongoClient
from core.schemas.devices import (
  CameraResponse,
  CameraStatusResponse,
  DetectionZoneCreate,
  DetectionZoneResponse,
  DetectionZoneUpdate,
)
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo import ASCENDING, DESCENDING

router = APIRouter(tags=["Cameras"])


@router.get(
  "/{camera_id}",
  response_model=CameraResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_camera(
  camera_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Fetch a camera scoped to the authenticated account."""
  db = mongo.get_database("barnsight")
  camera = await db["cameras"].find_one({"account_id": owner_id, "camera_id": camera_id})
  if not camera:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
  _serialize_id(camera)
  camera["online"] = await _camera_online(owner_id, camera_id)
  return camera


@router.get(
  "/{camera_id}/status",
  response_model=CameraStatusResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_camera_status(
  camera_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return online/offline status for a camera worker."""
  db = mongo.get_database("barnsight")
  camera = await db["cameras"].find_one({"account_id": owner_id, "camera_id": camera_id})
  online = await _camera_online(owner_id, camera_id)
  return {
    "camera_id": camera_id,
    "device_id": camera.get("device_id") if camera else None,
    "status": camera.get("status", "offline") if online and camera else "offline",
    "online": online,
    "last_seen_at": camera.get("last_seen_at") if camera else None,
    "heartbeat_ttl_seconds": settings.DEVICE_HEARTBEAT_TTL_SECONDS,
  }


async def _require_camera(db, owner_id: str, camera_id: str) -> dict:
  camera = await db["cameras"].find_one({"account_id": owner_id, "camera_id": camera_id})
  if not camera:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
  return camera


@router.get(
  "/{camera_id}/zones",
  response_model=list[DetectionZoneResponse],
  dependencies=[Depends(limit_dependency)],
)
async def list_camera_zones(
  camera_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """List floor zones for one camera perspective."""
  db = mongo.get_database("barnsight")
  await _require_camera(db, owner_id, camera_id)
  cursor = (
    db["detection_zones"]
    .find({"account_id": owner_id, "camera_id": camera_id})
    .sort("zone_id", ASCENDING)
  )
  zones = await cursor.to_list(length=None)
  return [_serialize_id(zone) for zone in zones]


@router.post(
  "/{camera_id}/zones",
  response_model=DetectionZoneResponse,
  status_code=status.HTTP_201_CREATED,
  dependencies=[Depends(limit_dependency)],
)
async def create_camera_zone(
  camera_id: str,
  zone: DetectionZoneCreate,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Create or update a camera-scoped floor zone."""
  if zone.camera_id != camera_id:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="camera_id mismatch")
  db = mongo.get_database("barnsight")
  camera = await _require_camera(db, owner_id, camera_id)
  if camera["device_id"] != zone.device_id or camera["barn_id"] != zone.barn_id:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="zone scope mismatch")

  now = _now()
  data = zone.model_dump()
  data.update({"account_id": owner_id, "created_at": now, "updated_at": now})
  await db["detection_zones"].update_one(
    {"account_id": owner_id, "camera_id": camera_id, "zone_id": zone.zone_id},
    {"$set": data, "$setOnInsert": {"created_at": now}},
    upsert=True,
  )
  saved = await db["detection_zones"].find_one(
    {"account_id": owner_id, "camera_id": camera_id, "zone_id": zone.zone_id}
  )
  return _serialize_id(saved) or data


@router.put(
  "/{camera_id}/zones/{zone_id}",
  response_model=DetectionZoneResponse,
  dependencies=[Depends(limit_dependency)],
)
async def update_camera_zone(
  camera_id: str,
  zone_id: str,
  zone: DetectionZoneUpdate,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Update a camera-scoped floor zone."""
  db = mongo.get_database("barnsight")
  await _require_camera(db, owner_id, camera_id)
  update = zone.model_dump(exclude_none=True)
  if "camera_id" in update and update["camera_id"] != camera_id:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="camera_id mismatch")
  if not update:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates supplied")
  update["updated_at"] = _now()
  result = await db["detection_zones"].update_one(
    {"account_id": owner_id, "camera_id": camera_id, "zone_id": zone_id},
    {"$set": update},
  )
  if result.modified_count == 0:
    existing = await db["detection_zones"].find_one(
      {"account_id": owner_id, "camera_id": camera_id, "zone_id": zone_id}
    )
    if not existing:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
  saved = await db["detection_zones"].find_one(
    {"account_id": owner_id, "camera_id": camera_id, "zone_id": zone_id}
  )
  return _serialize_id(saved)


@router.delete(
  "/{camera_id}/zones/{zone_id}",
  status_code=status.HTTP_204_NO_CONTENT,
  dependencies=[Depends(limit_dependency)],
)
async def delete_camera_zone(
  camera_id: str,
  zone_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Delete a zone scoped to one camera."""
  db = mongo.get_database("barnsight")
  await _require_camera(db, owner_id, camera_id)
  result = await db["detection_zones"].delete_one(
    {"account_id": owner_id, "camera_id": camera_id, "zone_id": zone_id}
  )
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
  return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{camera_id}/detections", dependencies=[Depends(limit_dependency)])
async def get_camera_detections(
  camera_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  limit: int = 100,
):
  """Return recent detection events for a camera."""
  db = mongo.get_database("barnsight")
  await _require_camera(db, owner_id, camera_id)
  cursor = (
    db["events"]
    .find({"account_id": owner_id, "camera_id": camera_id})
    .sort("timestamp", DESCENDING)
    .limit(limit)
  )
  events = await cursor.to_list(length=limit)
  for event in events:
    _serialize_id(event)
  return {"events": events}

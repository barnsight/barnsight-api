"""Physical edge device and camera management routes."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from api.auth_dependencies import validate_api_key
from api.dependencies import get_jwt_payload, get_mongo_client, limit_dependency
from core.config import settings
from core.database import MongoClient, RedisClient
from core.schemas.devices import (
  CameraCreate,
  CameraResponse,
  DetectionZoneCreate,
  DetectionZoneResponse,
  DetectionZoneUpdate,
  DeviceConfig,
  DeviceConfigResponse,
  DeviceCreate,
  DeviceHeartbeat,
  DeviceResponse,
  DeviceStatusResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from pymongo import ASCENDING

router = APIRouter(tags=["Devices"])

optional_oauth2_scheme = OAuth2PasswordBearer(
  tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False
)


async def get_device_owner(
  request: Request,
  api_key_data: Annotated[Optional[dict], Depends(validate_api_key)],
  token: Annotated[Optional[str], Depends(optional_oauth2_scheme)],
):
  """Return account owner from an edge API key or JWT."""
  if api_key_data:
    return api_key_data.get("owner_id")

  payload = get_jwt_payload(request)
  if payload:
    return payload.get("sub")

  raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Missing authentication (API Key or JWT)",
  )


def _now() -> datetime:
  return datetime.now(timezone.utc)


def _serialize_id(document: Optional[dict]) -> Optional[dict]:
  if document and document.get("_id") is not None:
    document["_id"] = str(document["_id"])
  return document


async def _camera_online(owner_id: str, camera_id: str) -> bool:
  redis = RedisClient()
  return bool(await redis.get(f"camera:{owner_id}:{camera_id}:status"))


async def _device_online(owner_id: str, device_id: str, db) -> bool:
  cursor = db["cameras"].find({"account_id": owner_id, "device_id": device_id})
  cameras = await cursor.to_list(length=None)
  for camera in cameras:
    if await _camera_online(owner_id, camera["camera_id"]):
      return True
  return False


async def _device_status_payload(owner_id: str, device: Optional[dict], device_id: str, db) -> dict:
  online = await _device_online(owner_id, device_id, db)
  return {
    "device_id": device_id,
    "status": device.get("status", "offline") if online and device else "offline",
    "online": online,
    "last_seen_at": device.get("last_seen_at") if device else None,
    "heartbeat_ttl_seconds": settings.DEVICE_HEARTBEAT_TTL_SECONDS,
  }


async def _ensure_device(db, owner_id: str, device_id: str, barn_id: Optional[str]) -> dict:
  now = _now()
  device = await db["devices"].find_one({"account_id": owner_id, "device_id": device_id})
  if device:
    return device
  device = {
    "account_id": owner_id,
    "device_id": device_id,
    "barn_id": barn_id or "unknown",
    "name": device_id,
    "location": None,
    "status": "offline",
    "last_seen_at": None,
    "created_at": now,
    "updated_at": now,
  }
  await db["devices"].insert_one(device)
  return device


async def _ensure_camera(
  db,
  owner_id: str,
  camera_id: str,
  device_id: str,
  barn_id: Optional[str],
) -> dict:
  now = _now()
  camera = await db["cameras"].find_one({"account_id": owner_id, "camera_id": camera_id})
  if camera:
    return camera
  camera = {
    "account_id": owner_id,
    "camera_id": camera_id,
    "device_id": device_id,
    "barn_id": barn_id or "unknown",
    "name": camera_id,
    "stream_label": None,
    "status": "offline",
    "last_seen_at": None,
    "created_at": now,
    "updated_at": now,
  }
  await db["cameras"].insert_one(camera)
  return camera


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
  device: DeviceCreate,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Create or update a physical edge host/gateway."""
  db = mongo.get_database("barnsight")
  now = _now()
  data = device.model_dump()
  data.update({"account_id": owner_id, "updated_at": now})
  await db["devices"].update_one(
    {"account_id": owner_id, "device_id": device.device_id},
    {"$set": data, "$setOnInsert": {"created_at": now, "last_seen_at": None}},
    upsert=True,
  )
  saved = await db["devices"].find_one({"account_id": owner_id, "device_id": device.device_id})
  saved = _serialize_id(saved) or {**data, "created_at": now, "last_seen_at": None}
  saved["online"] = await _device_online(owner_id, device.device_id, db)
  return saved


@router.get("", response_model=list[DeviceResponse], dependencies=[Depends(limit_dependency)])
async def list_devices(
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  barn_id: Optional[str] = Query(None),
):
  """List physical devices scoped to the authenticated account."""
  db = mongo.get_database("barnsight")
  query = {"account_id": owner_id}
  if barn_id:
    query["barn_id"] = barn_id
  cursor = db["devices"].find(query).sort("device_id", ASCENDING)
  devices = await cursor.to_list(length=None)
  for device in devices:
    _serialize_id(device)
    device["online"] = await _device_online(owner_id, device["device_id"], db)
  return devices


@router.post(
  "/heartbeat",
  status_code=status.HTTP_204_NO_CONTENT,
  dependencies=[Depends(limit_dependency)],
)
async def device_heartbeat(
  heartbeat: DeviceHeartbeat,
  api_key_data: Annotated[dict, Depends(validate_api_key)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Update physical device and camera status from one camera worker heartbeat."""
  if not api_key_data:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API Key")

  owner_id = api_key_data.get("owner_id")
  now = _now()
  db = mongo.get_database("barnsight")
  await _ensure_device(db, owner_id, heartbeat.device_id, heartbeat.barn_id)
  await _ensure_camera(db, owner_id, heartbeat.camera_id, heartbeat.device_id, heartbeat.barn_id)

  heartbeat_data = heartbeat.model_dump(exclude_none=True)
  camera_update = {
    **heartbeat_data,
    "account_id": owner_id,
    "last_seen_at": now,
    "updated_at": now,
  }
  device_update = {
    "account_id": owner_id,
    "device_id": heartbeat.device_id,
    "barn_id": heartbeat.barn_id or "unknown",
    "status": heartbeat.status,
    "last_seen_at": now,
    "updated_at": now,
  }

  await db["devices"].update_one(
    {"account_id": owner_id, "device_id": heartbeat.device_id},
    {"$set": device_update, "$setOnInsert": {"created_at": now, "name": heartbeat.device_id}},
    upsert=True,
  )
  await db["cameras"].update_one(
    {"account_id": owner_id, "camera_id": heartbeat.camera_id},
    {"$set": camera_update, "$setOnInsert": {"created_at": now, "name": heartbeat.camera_id}},
    upsert=True,
  )

  redis = RedisClient()
  ttl = settings.DEVICE_HEARTBEAT_TTL_SECONDS
  await redis.setex(f"camera:{owner_id}:{heartbeat.camera_id}:status", ttl, heartbeat.status)
  await redis.setex(f"device:{owner_id}:{heartbeat.device_id}:status", ttl, heartbeat.status)
  return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
  "/{device_id}/cameras",
  response_model=CameraResponse,
  status_code=status.HTTP_201_CREATED,
  dependencies=[Depends(limit_dependency)],
)
async def create_device_camera(
  device_id: str,
  camera: CameraCreate,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Create or update a camera attached to a physical device."""
  if camera.device_id != device_id:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="device_id mismatch")
  db = mongo.get_database("barnsight")
  await _ensure_device(db, owner_id, device_id, camera.barn_id)
  now = _now()
  data = camera.model_dump()
  data.update({"account_id": owner_id, "updated_at": now})
  await db["cameras"].update_one(
    {"account_id": owner_id, "camera_id": camera.camera_id},
    {"$set": data, "$setOnInsert": {"created_at": now, "last_seen_at": None}},
    upsert=True,
  )
  saved = await db["cameras"].find_one({"account_id": owner_id, "camera_id": camera.camera_id})
  saved = _serialize_id(saved) or {**data, "created_at": now, "last_seen_at": None}
  saved["online"] = await _camera_online(owner_id, camera.camera_id)
  return saved


@router.get(
  "/{device_id}/cameras",
  response_model=list[CameraResponse],
  dependencies=[Depends(limit_dependency)],
)
async def list_device_cameras(
  device_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """List cameras attached to a physical device."""
  db = mongo.get_database("barnsight")
  cursor = (
    db["cameras"]
    .find({"account_id": owner_id, "device_id": device_id})
    .sort("camera_id", ASCENDING)
  )
  cameras = await cursor.to_list(length=None)
  for camera in cameras:
    _serialize_id(camera)
    camera["online"] = await _camera_online(owner_id, camera["camera_id"])
  return cameras


@router.get(
  "/zones",
  response_model=list[DetectionZoneResponse],
  dependencies=[Depends(limit_dependency)],
)
async def list_zones(
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  camera_id: Optional[str] = Query(None),
  barn_id: Optional[str] = Query(None),
):
  """List detection zones, optionally filtered by camera or barn."""
  db = mongo.get_database("barnsight")
  query = {"account_id": owner_id}
  if camera_id:
    query["camera_id"] = camera_id
  if barn_id:
    query["barn_id"] = barn_id
  cursor = db["detection_zones"].find(query).sort("zone_id", ASCENDING)
  zones = await cursor.to_list(length=None)
  return [_serialize_id(zone) for zone in zones]


@router.post(
  "/zones",
  response_model=DetectionZoneResponse,
  status_code=status.HTTP_201_CREATED,
  dependencies=[Depends(limit_dependency)],
)
async def create_zone(
  zone: DetectionZoneCreate,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Create or update a camera floor detection zone."""
  db = mongo.get_database("barnsight")
  camera = await db["cameras"].find_one({"account_id": owner_id, "camera_id": zone.camera_id})
  if camera and camera.get("device_id") != zone.device_id:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="camera/device mismatch")
  now = _now()
  zone_data = zone.model_dump()
  zone_data.update({"account_id": owner_id, "created_at": now, "updated_at": now})
  await db["detection_zones"].update_one(
    {"account_id": owner_id, "camera_id": zone.camera_id, "zone_id": zone.zone_id},
    {"$set": zone_data, "$setOnInsert": {"created_at": now}},
    upsert=True,
  )
  saved = await db["detection_zones"].find_one(
    {"account_id": owner_id, "camera_id": zone.camera_id, "zone_id": zone.zone_id}
  )
  return _serialize_id(saved) or zone_data


@router.put(
  "/zones/{zone_id}",
  response_model=DetectionZoneResponse,
  dependencies=[Depends(limit_dependency)],
)
async def update_zone(
  zone_id: str,
  zone: DetectionZoneUpdate,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  camera_id: str = Query(...),
):
  """Update a camera floor detection zone."""
  db = mongo.get_database("barnsight")
  update = zone.model_dump(exclude_none=True)
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
  "/zones/{zone_id}",
  status_code=status.HTTP_204_NO_CONTENT,
  dependencies=[Depends(limit_dependency)],
)
async def delete_zone(
  zone_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  camera_id: str = Query(...),
):
  """Delete a detection zone scoped to one camera."""
  db = mongo.get_database("barnsight")
  result = await db["detection_zones"].delete_one(
    {"account_id": owner_id, "camera_id": camera_id, "zone_id": zone_id}
  )
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
  return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
  "/{device_id}",
  response_model=DeviceResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_device(
  device_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Fetch a physical edge device scoped to the authenticated account."""
  db = mongo.get_database("barnsight")
  device = await db["devices"].find_one({"account_id": owner_id, "device_id": device_id})
  if not device:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
  _serialize_id(device)
  device["online"] = await _device_online(owner_id, device_id, db)
  return device


@router.get(
  "/{device_id}/status",
  response_model=DeviceStatusResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_device_status(
  device_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return online/offline status for a physical device."""
  db = mongo.get_database("barnsight")
  device = await db["devices"].find_one({"account_id": owner_id, "device_id": device_id})
  return await _device_status_payload(owner_id, device, device_id, db)


@router.get(
  "/{device_id}/config",
  response_model=DeviceConfigResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_device_config(
  device_id: str,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return stored config or a validated default config for an edge device."""
  db = mongo.get_database("barnsight")
  config = await db["device_configs"].find_one({"account_id": owner_id, "device_id": device_id})
  if not config:
    config = DeviceConfig().model_dump()
    config.update({"account_id": owner_id, "device_id": device_id, "updated_at": _now()})
  _serialize_id(config)
  return config


@router.put(
  "/{device_id}/config",
  response_model=DeviceConfigResponse,
  dependencies=[Depends(limit_dependency)],
)
async def put_device_config(
  device_id: str,
  config: DeviceConfig,
  owner_id: Annotated[str, Depends(get_device_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Create or replace the remote configuration for an edge device."""
  db = mongo.get_database("barnsight")
  config_data = config.model_dump()
  config_data["updated_at"] = _now()
  config_data["account_id"] = owner_id
  config_data["device_id"] = device_id
  await db["device_configs"].update_one(
    {"account_id": owner_id, "device_id": device_id},
    {"$set": config_data},
    upsert=True,
  )
  saved = await db["device_configs"].find_one({"account_id": owner_id, "device_id": device_id})
  return _serialize_id(saved) or config_data

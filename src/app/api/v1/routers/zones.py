"""Top-level zone management routes."""

from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from api.v1.routers.devices import _serialize_id
from core.database import MongoClient
from core.permissions import require_permission, scoped_query
from core.schemas.devices import DetectionZoneUpdate
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo import ASCENDING

router = APIRouter(tags=["Zones"])


@router.get("", dependencies=[Depends(limit_dependency)])
async def list_zones(
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  camera_id: str | None = Query(None),
  barn_id: str | None = Query(None),
):
  require_permission(user, ["zones:read", "zones:manage"])
  db = mongo.get_database("barnsight")
  query = scoped_query(user)
  if camera_id:
    query["camera_id"] = camera_id
  if barn_id:
    query["barn_id"] = barn_id
  cursor = db["detection_zones"].find(query).sort("zone_id", ASCENDING)
  zones = await cursor.to_list(length=None)
  return {"zones": [_serialize_id(zone) for zone in zones]}


@router.get("/{zone_id}", dependencies=[Depends(limit_dependency)])
async def get_zone(
  zone_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  camera_id: str | None = Query(None),
):
  require_permission(user, ["zones:read", "zones:manage"])
  db = mongo.get_database("barnsight")
  query = scoped_query(user, {"zone_id": zone_id})
  if camera_id:
    query["camera_id"] = camera_id
  zone = await db["detection_zones"].find_one(query)
  if not zone:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
  return _serialize_id(zone)


@router.put("/{zone_id}", dependencies=[Depends(limit_dependency)])
async def update_zone(
  zone_id: str,
  update: DetectionZoneUpdate,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  camera_id: str = Query(...),
):
  require_permission(user, "zones:manage")
  db = mongo.get_database("barnsight")
  data = update.model_dump(exclude_none=True)
  if not data:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates supplied")
  result = await db["detection_zones"].update_one(
    scoped_query(user, {"camera_id": camera_id, "zone_id": zone_id}), {"$set": data}
  )
  if result.modified_count == 0:
    existing = await db["detection_zones"].find_one(
      scoped_query(user, {"camera_id": camera_id, "zone_id": zone_id})
    )
    if not existing:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
  saved = await db["detection_zones"].find_one(
    scoped_query(user, {"camera_id": camera_id, "zone_id": zone_id})
  )
  return _serialize_id(saved)


@router.delete(
  "/{zone_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def delete_zone(
  zone_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  camera_id: str = Query(...),
):
  require_permission(user, "zones:manage")
  db = mongo.get_database("barnsight")
  result = await db["detection_zones"].delete_one(
    scoped_query(user, {"camera_id": camera_id, "zone_id": zone_id})
  )
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
  return Response(status_code=status.HTTP_204_NO_CONTENT)

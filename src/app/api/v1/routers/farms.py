"""Farm management routes."""

from datetime import datetime, timezone
from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.permissions import (
  account_id_from_user,
  farm_id_from_user,
  require_permission,
  scoped_query,
)
from core.schemas.platform import FarmCreate, FarmUpdate
from core.services.audit_service import write_audit_log
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo import ASCENDING

router = APIRouter(tags=["Farms"])


def _now() -> datetime:
  return datetime.now(timezone.utc)


def _serialize(doc: dict | None) -> dict | None:
  if doc and doc.get("_id") is not None:
    doc["_id"] = str(doc["_id"])
  return doc


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit_dependency)])
async def create_farm(
  farm: FarmCreate,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(user, "farms:manage")
  db = mongo.get_database("barnsight")
  now = _now()
  account_id = farm.account_id or account_id_from_user(user)
  farm_id = farm.farm_id or farm.name.lower().replace(" ", "-")
  doc = {
    **farm.model_dump(exclude_none=True),
    "account_id": account_id,
    "farm_id": farm_id,
    "status": "active",
    "created_at": now,
    "updated_at": now,
  }
  await db["farms"].update_one(
    {"account_id": account_id, "farm_id": farm_id},
    {"$set": doc, "$setOnInsert": {"created_at": now}},
    upsert=True,
  )
  await write_audit_log(
    db,
    action="farm.created",
    actor_id=user.get("username"),
    account_id=account_id,
    farm_id=farm_id,
    resource_type="farm",
    resource_id=farm_id,
  )
  saved = await db["farms"].find_one({"account_id": account_id, "farm_id": farm_id})
  return _serialize(saved)


@router.get("", dependencies=[Depends(limit_dependency)])
async def list_farms(
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(user, ["farms:read", "farms:manage", "accounts:read"])
  db = mongo.get_database("barnsight")
  cursor = db["farms"].find(scoped_query(user)).sort("name", ASCENDING)
  farms = await cursor.to_list(length=None)
  return {"farms": [_serialize(farm) for farm in farms]}


@router.get("/{farm_id}", dependencies=[Depends(limit_dependency)])
async def get_farm(
  farm_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(user, ["farms:read", "farms:manage", "accounts:read"])
  db = mongo.get_database("barnsight")
  farm = await db["farms"].find_one(scoped_query(user, {"farm_id": farm_id}))
  if not farm:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")
  return _serialize(farm)


@router.patch("/{farm_id}", dependencies=[Depends(limit_dependency)])
async def update_farm(
  farm_id: str,
  update: FarmUpdate,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(user, "farms:manage")
  db = mongo.get_database("barnsight")
  data = update.model_dump(exclude_none=True)
  if not data:
    return {"message": "No fields to update."}
  data["updated_at"] = _now()
  result = await db["farms"].update_one(scoped_query(user, {"farm_id": farm_id}), {"$set": data})
  if result.modified_count == 0:
    existing = await db["farms"].find_one(scoped_query(user, {"farm_id": farm_id}))
    if not existing:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")
  await write_audit_log(
    db,
    action="farm.updated",
    actor_id=user.get("username"),
    account_id=account_id_from_user(user),
    farm_id=farm_id_from_user(user),
    resource_type="farm",
    resource_id=farm_id,
  )
  saved = await db["farms"].find_one(scoped_query(user, {"farm_id": farm_id}))
  return _serialize(saved)


@router.delete(
  "/{farm_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def delete_farm(
  farm_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(user, "farms:manage")
  db = mongo.get_database("barnsight")
  result = await db["farms"].delete_one(scoped_query(user, {"farm_id": farm_id}))
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")
  await write_audit_log(
    db,
    action="farm.deleted",
    actor_id=user.get("username"),
    account_id=account_id_from_user(user),
    farm_id=farm_id,
    resource_type="farm",
    resource_id=farm_id,
  )
  return Response(status_code=status.HTTP_204_NO_CONTENT)

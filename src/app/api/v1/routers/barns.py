"""Barn management routes.

Handles listing and retrieving barns with their zones and cameras.
"""

from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.permissions import (
  account_id_from_user,
  farm_id_from_user,
  require_permission,
  scoped_query,
)
from core.schemas.barns import BarnListResponse, BarnResponse
from core.schemas.platform import BarnUpdate, BarnWrite
from core.services.audit_service import write_audit_log
from crud.barn_crud import BarnCRUD
from crud.event_crud import EventCRUD
from fastapi import APIRouter, Depends, HTTPException, Response, status

router = APIRouter(tags=["Barns"])


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit_dependency)])
async def create_barn(
  barn: BarnWrite,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(user, "barns:manage")
  db = mongo.get_database("barnsight")
  data = barn.model_dump()
  data["account_id"] = account_id_from_user(user)
  data["farm_id"] = barn.farm_id or farm_id_from_user(user)
  data.setdefault("zones", [])
  await db["barns"].update_one(
    {"account_id": data["account_id"], "barn_id": barn.barn_id},
    {"$set": data},
    upsert=True,
  )
  await write_audit_log(
    db,
    action="barn.created",
    actor_id=user.get("username"),
    account_id=data["account_id"],
    farm_id=data["farm_id"],
    resource_type="barn",
    resource_id=barn.barn_id,
  )
  saved = await db["barns"].find_one({"account_id": data["account_id"], "barn_id": barn.barn_id})
  saved["_id"] = str(saved["_id"])
  return saved


@router.get(
  "",
  status_code=status.HTTP_200_OK,
  response_model=BarnListResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_barns(
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return all barns accessible to the user."""
  db = mongo.get_database("barnsight")
  barn_crud = BarnCRUD(db)

  username = user.get("username")
  role = user.get("role", "")
  account_id = user.get("sub")

  barn_ids = await barn_crud.get_barn_ids_for_user(username, role)
  all_barns = await barn_crud.get_all_barns(account_id=account_id)

  if barn_ids is not None:
    all_barns = [b for b in all_barns if b["barn_id"] in barn_ids]

  return {"barns": all_barns}


@router.get(
  "/{barn_id}",
  status_code=status.HTTP_200_OK,
  response_model=BarnResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_barn(
  barn_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return a single barn by ID with its zones and cameras."""
  db = mongo.get_database("barnsight")
  barn_crud = BarnCRUD(db)

  username = user.get("username")
  role = user.get("role", "")
  account_id = user.get("sub")

  barn_ids = await barn_crud.get_barn_ids_for_user(username, role)

  if barn_ids is not None and barn_id not in barn_ids:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Access denied to this barn.",
    )

  lookup_barn_id = int(barn_id) if barn_id.isdigit() else barn_id
  barn = await barn_crud.get_barn_by_id(lookup_barn_id, account_id=account_id)
  if not barn:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail="Barn not found.",
    )

  return barn


@router.patch("/{barn_id}", dependencies=[Depends(limit_dependency)])
async def update_barn(
  barn_id: str,
  update: BarnUpdate,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(user, "barns:manage")
  db = mongo.get_database("barnsight")
  data = update.model_dump(exclude_none=True)
  if not data:
    return {"message": "No fields to update."}
  result = await db["barns"].update_one(scoped_query(user, {"barn_id": barn_id}), {"$set": data})
  if result.modified_count == 0:
    existing = await db["barns"].find_one(scoped_query(user, {"barn_id": barn_id}))
    if not existing:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Barn not found")
  await write_audit_log(
    db,
    action="barn.updated",
    actor_id=user.get("username"),
    account_id=account_id_from_user(user),
    farm_id=farm_id_from_user(user),
    resource_type="barn",
    resource_id=barn_id,
  )
  saved = await db["barns"].find_one(scoped_query(user, {"barn_id": barn_id}))
  saved["_id"] = str(saved["_id"])
  return saved


@router.delete(
  "/{barn_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def delete_barn(
  barn_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(user, "barns:manage")
  db = mongo.get_database("barnsight")
  result = await db["barns"].delete_one(scoped_query(user, {"barn_id": barn_id}))
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Barn not found")
  await write_audit_log(
    db,
    action="barn.deleted",
    actor_id=user.get("username"),
    account_id=account_id_from_user(user),
    farm_id=farm_id_from_user(user),
    resource_type="barn",
    resource_id=barn_id,
  )
  return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{barn_id}/summary", dependencies=[Depends(limit_dependency)])
async def get_barn_summary(
  barn_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  account_id = _account_id_from_user(user)
  barn = await db["barns"].find_one({"account_id": account_id, "barn_id": barn_id})
  events_count = await db["events"].count_documents({"account_id": account_id, "barn_id": barn_id})
  devices_count = await db["devices"].count_documents(
    {"account_id": account_id, "barn_id": barn_id}
  )
  cameras_count = await db["cameras"].count_documents(
    {"account_id": account_id, "barn_id": barn_id}
  )
  return {
    "barn": barn,
    "events_count": events_count,
    "devices_count": devices_count,
    "cameras_count": cameras_count,
  }


@router.get("/{barn_id}/events", dependencies=[Depends(limit_dependency)])
async def get_barn_events(
  barn_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  account_id = _account_id_from_user(user)
  cursor = db["events"].find({"account_id": account_id, "barn_id": barn_id}).sort("_id", -1)
  events = await cursor.to_list(length=100)
  for event in events:
    event["_id"] = str(event["_id"])
  return {"events": events}


def _account_id_from_user(user: dict) -> str | None:
  return user.get("sub") or user.get("username")


@router.get("/{barn_id}/devices", dependencies=[Depends(limit_dependency)])
async def get_barn_devices(
  barn_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """List devices for one barn scoped to the authenticated account."""
  db = mongo.get_database("barnsight")
  query = {"account_id": _account_id_from_user(user), "barn_id": barn_id}
  cursor = db["devices"].find(query)
  devices = await cursor.to_list(length=None)
  for device in devices:
    device["_id"] = str(device["_id"])
  return {"devices": devices}


@router.get("/{barn_id}/cameras", dependencies=[Depends(limit_dependency)])
async def get_barn_cameras(
  barn_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """List cameras for one barn scoped to the authenticated account."""
  db = mongo.get_database("barnsight")
  query = {"account_id": _account_id_from_user(user), "barn_id": barn_id}
  cursor = db["cameras"].find(query)
  cameras = await cursor.to_list(length=None)
  for camera in cameras:
    camera["_id"] = str(camera["_id"])
  return {"cameras": cameras}


@router.get("/{barn_id}/hygiene-summary", dependencies=[Depends(limit_dependency)])
async def get_barn_hygiene_summary(
  barn_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return a barn-scoped hygiene analytics summary."""
  db = mongo.get_database("barnsight")
  account_id = _account_id_from_user(user)
  analytics = await EventCRUD(db).get_analytics(account_id=account_id, barn_id=barn_id)
  return analytics

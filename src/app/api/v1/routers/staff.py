"""Staff management routes."""

from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.platform import GenericPatch, StaffBarnAssignment
from core.schemas.registration import StaffCreate
from crud import UserCRUD
from fastapi import APIRouter, Body, Depends, HTTPException, Response, Security, status

router = APIRouter(tags=["Staff"])


@router.post(
  "",
  status_code=status.HTTP_201_CREATED,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def register_staff(
  staff: Annotated[StaffCreate, Body()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Register a new staff account. Admin only."""
  users_db = mongo.get_database("users")
  if await UserCRUD(users_db).find(username=staff.username):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Username already exists.",
    )

  await UserCRUD(users_db).create(staff)
  return {"message": "Staff account created successfully."}


@router.get("", status_code=status.HTTP_200_OK, dependencies=[Depends(limit_dependency)])
async def list_staff(
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  cursor = users_db["staff"].find({})
  staff = await cursor.to_list(length=None)
  for member in staff:
    member["_id"] = str(member["_id"])
    member.pop("password", None)
  return {"staff": staff}


@router.get("/{staff_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(limit_dependency)])
async def get_staff(
  staff_id: str,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  member = await users_db["staff"].find_one({"username": staff_id})
  if not member:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
  member["_id"] = str(member["_id"])
  member.pop("password", None)
  return member


@router.patch(
  "/{staff_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(limit_dependency)]
)
async def update_staff(
  staff_id: str,
  update: GenericPatch,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  data = update.model_dump(exclude_unset=True)
  data.pop("password", None)
  result = await users_db["staff"].update_one({"username": staff_id}, {"$set": data})
  if result.modified_count == 0:
    existing = await users_db["staff"].find_one({"username": staff_id})
    if not existing:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
  return {"message": "Staff member updated."}


@router.delete(
  "/{staff_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def delete_staff(
  staff_id: str,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  result = await users_db["staff"].delete_one({"username": staff_id})
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
  return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
  "/{staff_id}/assign-barns",
  status_code=status.HTTP_200_OK,
  dependencies=[Depends(limit_dependency)],
)
async def assign_staff_barns(
  staff_id: str,
  assignment: StaffBarnAssignment,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  result = await users_db["staff"].update_one(
    {"username": staff_id}, {"$set": {"assigned_barn_ids": assignment.barn_ids}}
  )
  if result.modified_count == 0:
    existing = await users_db["staff"].find_one({"username": staff_id})
    if not existing:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
  return {"message": "Barn assignments updated.", "barn_ids": assignment.barn_ids}

"""Staff management routes."""

from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.registration import StaffCreate
from crud import UserCRUD
from fastapi import APIRouter, Body, Depends, HTTPException, Security, status

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

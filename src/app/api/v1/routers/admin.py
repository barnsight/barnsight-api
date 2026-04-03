"""Admin management routes.

Handles initial admin setup, dashboard stats, user role changes,
and registration of farmer/staff accounts.
All endpoints require admin scope except /setup.
"""

from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.admin import AdminCreate
from core.schemas.registration import FarmerCreate, StaffCreate
from crud import UserCRUD
from fastapi import APIRouter, Body, Depends, HTTPException, Security, status

router = APIRouter(tags=["Admin"])


@router.post(
  "/setup",
  status_code=status.HTTP_201_CREATED,
  dependencies=[Depends(limit_dependency)],
)
async def create_admin_account(
  admin: Annotated[AdminCreate, Body()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Create the initial admin account. One-time setup endpoint."""
  users_db = mongo.get_database("users")
  if await UserCRUD(users_db).find(username=admin.username):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Admin already exists.",
    )

  await UserCRUD(users_db).create(admin)
  return {"message": "Admin account created successfully."}


@router.post(
  "/register/farmer",
  status_code=status.HTTP_201_CREATED,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def register_farmer(
  farmer: Annotated[FarmerCreate, Body()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Register a new farmer account. Admin only."""
  users_db = mongo.get_database("users")
  if await UserCRUD(users_db).find(username=farmer.username):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Username already exists.",
    )

  await UserCRUD(users_db).create(farmer)
  return {"message": "Farmer account created successfully."}


@router.post(
  "/register/staff",
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


@router.get(
  "/dashboard",
  status_code=status.HTTP_200_OK,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def admin_dashboard(
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return system-wide statistics for the admin dashboard."""
  users_db = mongo.get_database("users")
  barnsight_db = mongo.get_database("barnsight")

  return {
    "users": {
      "admins": await users_db["admins"].count_documents({}),
      "farmers": await users_db["farmers"].count_documents({}),
      "staff": await users_db["staff"].count_documents({}),
      "edge_devices": await users_db["edge"].count_documents({}),
    },
    "events": {
      "total": await barnsight_db["events"].count_documents({}),
    },
  }


@router.patch(
  "/users/{username}/role",
  status_code=status.HTTP_200_OK,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def change_user_role(
  username: str,
  new_role: Annotated[str, Body(embed=True)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Change a user's role and migrate their document between collections."""
  users_db = mongo.get_database("users")
  user_crud = UserCRUD(users_db)

  user = await user_crud.find(username=username)
  if not user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

  old_role = user.get("role")
  if old_role == new_role:
    return {"message": f"User is already a {new_role}"}

  user["role"] = new_role
  if new_role == "admins":
    user["scopes"] = ["admin"]
  elif new_role == "farmers":
    user["scopes"] = ["farmer"]
  elif new_role == "staff":
    user["scopes"] = ["staff"]
  elif new_role == "edge":
    user["scopes"] = ["edge"]
  else:
    user["scopes"] = ["staff"]

  # Atomic migration: insert into new collection, delete from old
  async with await mongo._client.start_session() as session:
    async with session.start_transaction():
      await users_db[new_role].insert_one(user, session=session)
      await users_db[old_role].delete_one({"username": username}, session=session)

  return {"message": f"User {username} role updated from {old_role} to {new_role}"}

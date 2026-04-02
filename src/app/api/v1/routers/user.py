"""User profile management routes.

Handles profile viewing, updates, password changes, and email management.
All endpoints require JWT authentication.
"""

from typing import Annotated

from fastapi import HTTPException, APIRouter, status, Depends, Body

from core.schemas.user import UserUpdate
from core.schemas.utils import UpdateEmail, UpdatePassword
from core.security.utils import Hash
from core.database import MongoClient, RedisClient
from api.dependencies import (
  get_mongo_client,
  get_redis_client,
  get_current_user,
  limit_dependency,
)
from crud import UserCRUD

router = APIRouter(tags=["User"])


@router.get(
  "/me",
  status_code=status.HTTP_200_OK,
  response_model_exclude={"password"},
  response_model_exclude_none=True,
  dependencies=[Depends(limit_dependency)],
)
async def get_active_user(
  user: Annotated[dict, Depends(get_current_user)],
):
  """Return the authenticated user's profile data."""
  return user


@router.patch(
  "/me",
  status_code=status.HTTP_200_OK,
  dependencies=[Depends(limit_dependency)],
)
async def update_user_profile(
  user_update: Annotated[UserUpdate, Body()],
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  """Update the current user's profile fields."""
  users_db = mongo.get_database("users")
  username = user.get("username")

  update_data = user_update.model_dump(exclude_unset=True)
  if not update_data:
    return {"message": "No fields to update."}

  if not await UserCRUD(users_db).update(username=username, update=update_data):
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail="User not found.",
    )

  await redis.delete(f"cache:user:{username}:profile")
  return {"message": "The profile was updated."}


@router.patch(
  "/me/password",
  status_code=status.HTTP_200_OK,
  dependencies=[Depends(limit_dependency)],
)
async def update_password(
  update_body: Annotated[UpdatePassword, Body()],
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Change the current user's password after verifying the current one."""
  users_db = mongo.get_database("users")
  username = user.get("username")

  if not await UserCRUD(users_db).authenticate(
    username=username, plain_pwd=update_body.current_password
  ):
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Couldn't validate credentials",
      headers={"WWW-Authenticate": "Bearer"},
    )

  await UserCRUD(users_db).update(
    username=username,
    update={"password": Hash.hash(plain=update_body.new_password)},
  )
  return {"message": "The password was updated."}


@router.patch(
  "/email",
  status_code=status.HTTP_200_OK,
  dependencies=[Depends(limit_dependency)],
)
async def update_email(
  user_update: Annotated[UpdateEmail, Body()],
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  """Add or change the user's email after password verification."""
  users_db = mongo.get_database("users")

  # Check email is not already in use
  if await UserCRUD(users_db).find(email=user_update.email):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="That email is already associated with another account.",
    )

  username = user.get("username")
  if not await UserCRUD(users_db).authenticate(
    username=username, plain_pwd=user_update.password
  ):
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Couldn't validate credentials",
      headers={"WWW-Authenticate": "Bearer"},
    )

  await UserCRUD(users_db).update(
    username=username,
    update={"email": {"address": user_update.email, "is_verified": False}},
  )
  await redis.delete(f"cache:user:{username}:profile")
  return {"message": "Email added to the user account."}

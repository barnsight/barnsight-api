import json
from datetime import timedelta
from typing import Annotated, List

from api.dependencies import get_current_user, get_mongo_client, get_redis_client, limit_dependency
from core.config import settings
from core.database import MongoClient, RedisClient
from core.logger import logger
from core.permissions import account_id_from_user, require_permission
from core.schemas.platform import UserCreate, UserRoleUpdate, UserStatusUpdate
from core.schemas.user import UserBase, UserUpdate
from core.services.audit_service import write_audit_log
from crud import UserCRUD
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Security, status

router = APIRouter(tags=["Users"])


@router.get(
  "",
  status_code=status.HTTP_200_OK,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def list_users(
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """List users visible to the current admin."""
  require_permission(current_user, "users:manage")
  users_db = mongo.get_database("users")
  users = []
  for role in await users_db.list_collection_names():
    if role in {"api_keys", "audit_logs", "password_reset_requests", "email_verifications"}:
      continue
    cursor = users_db[role].find({})
    docs = await cursor.to_list(length=None)
    for doc in docs:
      doc.pop("password", None)
      doc["_id"] = str(doc["_id"])
      users.append(doc)
  return {"users": users}


@router.post(
  "",
  status_code=status.HTTP_201_CREATED,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def create_user(
  body: Annotated[UserCreate, Body()],
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Create a platform user with role, scopes, farm assignment, and permissions."""
  require_permission(current_user, "users:manage")
  users_db = mongo.get_database("users")
  if await UserCRUD(users_db).find(username=body.username):
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists.")
  if not body.account_id:
    body.account_id = account_id_from_user(current_user)
  if not body.scopes:
    body.scopes = [body.role.removesuffix("s")]
  created = await UserCRUD(users_db).create(body)
  await write_audit_log(
    users_db,
    action="user.created",
    actor_id=current_user.get("username"),
    account_id=body.account_id,
    resource_type="user",
    resource_id=body.username,
  )
  data = created.model_dump()
  data.pop("password", None)
  return data


@router.get(
  "/{username}",
  status_code=status.HTTP_200_OK,
  response_model=UserBase,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def read_user(
  username: Annotated[str, Path()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  """
  Returns user by `username`.
  """
  redis_key = f"cache:user:{username}:profile"

  # Check if user data exists in Redis cache
  if user_cache := await redis.get(redis_key):
    try:
      # Parse user data to the JSON format
      user = json.loads(user_cache)
    except json.JSONDecodeError as e:
      logger.error(
        {
          "message": "[x] An error occured while decoding user's data from Redis cache.",
          "detail": str(e),
        },
        exc_info=True,
      )
      pass
  else:
    # Check if user exists in MongoDB
    users_db = mongo.get_database("users")
    if not (user := await UserCRUD(users_db).find(username=username)):
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Store user data in Redis cache
    await redis.setex(
      redis_key,
      timedelta(minutes=settings.CACHE_EXPIRE_MINUTES).seconds,
      json.dumps(user, default=str),
    )

  return user


@router.get(
  "/all/{role}",
  status_code=status.HTTP_200_OK,
  response_model=List[UserBase],
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def read_users(
  role: Annotated[str, Path()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """
  Returns all users by role.
  """
  users_db = mongo.get_database("users")
  return await UserCRUD(users_db).read_all(role)


@router.patch(
  "/{username}",
  status_code=status.HTTP_200_OK,
  dependencies=[Security(get_current_user, scopes=["admin"])],
)
async def update_user(
  username: Annotated[str, Path()],
  update_user: Annotated[UserUpdate, Body()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  """
  Updates user data by `username`.
  """
  users_db = mongo.get_database("users")
  current = await UserCRUD(users_db).find(username=username)
  if not current:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

  # Update the user data
  await UserCRUD(users_db).update(
    username=username, update=update_user.model_dump(exclude_unset=True)
  )

  # Delete user profile from Redis cache
  await redis.delete(f"cache:user:{username}:profile")

  return {"message": "The user account has been updated."}


@router.patch(
  "/{username}/role",
  status_code=status.HTTP_200_OK,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def update_user_role(
  username: str,
  body: UserRoleUpdate,
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  require_permission(current_user, "users:manage")
  users_db = mongo.get_database("users")
  user = await UserCRUD(users_db).find(username=username)
  if not user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
  old_role = user.get("role")
  if old_role != body.role:
    user["role"] = body.role
    user["scopes"] = [body.role.removesuffix("s")]
    user.pop("_id", None)
    await users_db[body.role].insert_one(user)
    await users_db[old_role].delete_one({"username": username})
  await write_audit_log(
    users_db,
    action="user.role_changed",
    actor_id=current_user.get("username"),
    account_id=user.get("account_id"),
    resource_type="user",
    resource_id=username,
    metadata={"old_role": old_role, "new_role": body.role},
  )
  return {"message": f"User {username} role updated from {old_role} to {body.role}"}


@router.patch(
  "/{username}/status",
  status_code=status.HTTP_200_OK,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def update_user_status(
  username: str,
  body: UserStatusUpdate,
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  require_permission(current_user, "users:manage")
  users_db = mongo.get_database("users")
  if not await UserCRUD(users_db).update(username, {"status": body.status}):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
  await redis.delete(f"cache:user:{username}:profile")
  await write_audit_log(
    users_db,
    action="user.updated",
    actor_id=current_user.get("username"),
    resource_type="user",
    resource_id=username,
    metadata={"status": body.status},
  )
  return {"message": "User status updated."}


@router.delete(
  "/{username}",
  status_code=status.HTTP_200_OK,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def delete_user(
  username: Annotated[str, Path()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  """
  Deletes an exiting user account.
  """

  # Delete the user account
  users_db = mongo.get_database("users")
  if not await UserCRUD(users_db).delete(username=username):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

  # Delete user profile from Redis cache
  await redis.delete(f"cache:user:{username}:profile")

  return {"message": "The user account was deleted successfully."}

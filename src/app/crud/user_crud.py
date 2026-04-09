"""User CRUD operations for MongoDB.

Handles user lookup, creation, updates, deletion, and authentication.
Uses a single 'users' collection with role-based document separation.
"""

from typing import List, Optional, Union

from core.config import ModelType
from core.logger import logger
from core.security.utils import Hash

from .base_crud import BaseCRUD


class UserCRUD(BaseCRUD):
  """CRUD operations for user documents across role-based collections."""

  def __init__(self, db):
    super().__init__(db)

  async def find(
    self,
    *,
    username: Optional[str] = None,
    email: Optional[str] = None,
    exclude: Optional[List[str]] = None,
  ) -> Union[dict, None]:
    """Find a user by username or email.

    Searches the specific collection based on the query type
    rather than iterating all collections.
    """
    try:
      query = {}
      if username:
        query["username"] = username
      if email:
        query["email"] = email
      if not query:
        return None

      # Search all role collections (users, admins, edge)
      for collection in await self.db.list_collection_names():
        user = await self.db[collection].find_one(query)
        if user:
          if exclude:
            for key in exclude:
              user.pop(key, None)
          return user
      return None
    except Exception as e:
      logger.error(
        {"message": "Error searching user in MongoDB", "detail": str(e)},
        exc_info=True,
      )
      return None

  async def create(self, user: ModelType):
    """Create a new user with hashed password."""
    user.password = Hash.hash(plain=user.password)
    await self.db[user.role].insert_one(user.model_dump())
    return user

  async def update(self, username: str, update: dict) -> Union[dict, None]:
    """Update a user document by username.

    Uses username as the filter (not the entire document) to avoid
    race conditions where fields change between find and update.
    """
    user = await self.find(username=username)
    if not user:
      return None
    role = user.get("role")
    if not role:
      return None
    return await self.db[role].find_one_and_update(
      filter={"username": username},
      update={"$set": update},
    )

  async def delete(self, username: str):
    """Delete a user document by username."""
    user = await self.find(username=username)
    if not user:
      return 0
    role = user.get("role")
    if not role:
      return 0
    result = await self.db[role].delete_one({"username": username})
    return result.deleted_count

  async def authenticate(
    self,
    *,
    username: str,
    plain_pwd: str,
    exclude: Optional[List[str]] = None,
  ) -> Union[dict, None]:
    """Authenticate a user by verifying password hash."""
    user = await self.find(username=username)
    if not user or not Hash.verify(plain_pwd, user.get("password")):
      return None
    if exclude:
      for key in exclude:
        user.pop(key, None)
    return user

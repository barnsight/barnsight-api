"""Base CRUD operations for MongoDB collections.

Provides generic create, read, update, delete methods
that can be extended by collection-specific CRUD classes.
"""

from typing import Any, Optional

from pymongo.asynchronous.database import AsyncDatabase
from core.config import ModelType


class BaseCRUD:
  """Generic CRUD operations backed by an async MongoDB database."""

  def __init__(self, db: AsyncDatabase):
    self.db = db

  async def create(self, collection: str, model: ModelType):
    """Insert a single document into the collection."""
    return await self.db[collection].insert_one(model.model_dump())

  async def read(self, collection: str, filter: Any):
    """Find a single document matching the filter."""
    return await self.db[collection].find_one(filter)

  async def read_all(
    self,
    collection: str,
    *,
    filter: Optional[Any] = None,
    offset: int = 0,
    length: Optional[int] = None,
  ):
    """Find all documents matching the filter with pagination."""
    query = filter or {}
    objects = await self.db[collection].find(query).to_list(length)
    return objects[offset:] if objects else []

  async def update(
    self,
    collection: str,
    *,
    update: dict,
    filter: Optional[Any] = None,
  ):
    """Update a single document matching the filter."""
    query = filter or {}
    result = await self.db[collection].update_one(query, update={"$set": update})
    return result.modified_count

  async def update_all(
    self,
    collection: str,
    *,
    update: dict,
    filter: Optional[Any] = None,
  ) -> int:
    """Update all documents matching the filter."""
    query = filter or {}
    result = await self.db[collection].update_many(query, update={"$set": update})
    return result.modified_count

  async def delete(self, collection: str, filter: Optional[Any] = None):
    """Delete a single document matching the filter."""
    query = filter or {}
    result = await self.db[collection].delete_one(query)
    return result.deleted_count

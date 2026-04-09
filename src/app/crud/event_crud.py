from datetime import datetime
from typing import Optional

from core.schemas.events import EventCreate
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

from .base_crud import BaseCRUD


class EventCRUD(BaseCRUD):
  def __init__(self, db: AsyncDatabase):
    super().__init__(db)
    self.collection_name = "events"

  async def create_event(self, event: dict | EventCreate):
    """Creates a new detection event."""
    if hasattr(event, "model_dump"):
      event_dict = event.model_dump()
    else:
      event_dict = event
    result = await self.db[self.collection_name].insert_one(event_dict)
    event_dict["_id"] = str(result.inserted_id)
    return event_dict

  async def get_events(
    self,
    account_id: str,
    camera_id: Optional[str] = None,
    device_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    cursor: Optional[str] = None,
    limit: int = 100,
  ):
    """Reads events with cursor-based filtering."""
    from bson import ObjectId

    query = {"account_id": account_id}
    if camera_id:
      query["camera_id"] = camera_id
    if device_id:
      query["device_id"] = device_id

    if start_time or end_time:
      query["timestamp"] = {}
      if start_time:
        query["timestamp"]["$gte"] = start_time
      if end_time:
        query["timestamp"]["$lte"] = end_time

    if cursor:
      try:
        query["_id"] = {"$lt": ObjectId(cursor)}
      except Exception:
        pass  # Handle invalid cursor gracefully

    cursor_obj = (
      self.db[self.collection_name]
      .find(query)
      .sort("_id", DESCENDING)
      .limit(limit)
    )
    events = await cursor_obj.to_list(length=limit)

    # Convert ObjectId to string for response
    for event in events:
      event["_id"] = str(event["_id"])

    next_cursor = events[-1]["_id"] if events else None
    total = await self.db[self.collection_name].count_documents(query)
    return events, total, next_cursor

  async def get_analytics(self):
    """Aggregates basic analytics."""
    total_detections = await self.db[self.collection_name].count_documents({})

    camera_pipeline = [{"$group": {"_id": "$camera_id", "count": {"$sum": 1}}}]
    camera_cursor = await self.db[self.collection_name].aggregate(camera_pipeline)
    camera_stats = await camera_cursor.to_list(length=None)
    detections_by_camera = {stat["_id"]: stat["count"] for stat in camera_stats if stat["_id"]}

    device_pipeline = [{"$group": {"_id": "$device_id", "count": {"$sum": 1}}}]
    device_cursor = await self.db[self.collection_name].aggregate(device_pipeline)
    device_stats = await device_cursor.to_list(length=None)
    detections_by_device = {stat["_id"]: stat["count"] for stat in device_stats if stat["_id"]}

    return {
      "total_detections": total_detections,
      "detections_by_camera": detections_by_camera,
      "detections_by_device": detections_by_device,
    }

  async def setup_indexes(self):
    """Creates necessary indexes for the collection, including TTL."""
    # TTL Index: expireAfterSeconds = 90 days * 24 hours * 3600 seconds = 7,776,000
    await self.db[self.collection_name].create_index(
      [("timestamp", DESCENDING)], expireAfterSeconds=7776000
    )
    await self.db[self.collection_name].create_index(
      [("account_id", ASCENDING), ("_id", DESCENDING)]
    )
    await self.db[self.collection_name].create_index(
      [("camera_id", ASCENDING), ("timestamp", DESCENDING)]
    )
    await self.db[self.collection_name].create_index(
      [("device_id", ASCENDING), ("timestamp", DESCENDING)]
    )

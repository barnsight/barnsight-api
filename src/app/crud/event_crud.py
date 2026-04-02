from typing import List, Optional
from datetime import datetime
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

from .base_crud import BaseCRUD
from core.schemas.events import EventCreate

class EventCRUD(BaseCRUD):
  def __init__(self, db: AsyncDatabase):
    super().__init__(db)
    self.collection_name = "events"

  async def create_event(self, event: EventCreate):
    """Creates a new detection event."""
    event_dict = event.model_dump()
    result = await self.db[self.collection_name].insert_one(event_dict)
    event_dict["_id"] = str(result.inserted_id)
    return event_dict

  async def get_events(
    self,
    camera_id: Optional[str] = None,
    device_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    offset: int = 0,
    limit: int = 100
  ):
    """Reads events with filtering."""
    query = {}
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
        
    cursor = self.db[self.collection_name].find(query).sort("timestamp", DESCENDING).skip(offset).limit(limit)
    events = await cursor.to_list(length=limit)
    
    # Convert ObjectId to string for response
    for event in events:
      event["_id"] = str(event["_id"])
        
    total = await self.db[self.collection_name].count_documents(query)
    return events, total

  async def get_analytics(self):
    """Aggregates basic analytics."""
    total_detections = await self.db[self.collection_name].count_documents({})
    
    camera_pipeline = [
      {"$group": {"_id": "$camera_id", "count": {"$sum": 1}}}
    ]
    camera_cursor = await self.db[self.collection_name].aggregate(camera_pipeline)
    camera_stats = await camera_cursor.to_list(length=None)
    detections_by_camera = {stat["_id"]: stat["count"] for stat in camera_stats if stat["_id"]}

    device_pipeline = [
      {"$group": {"_id": "$device_id", "count": {"$sum": 1}}}
    ]
    device_cursor = await self.db[self.collection_name].aggregate(device_pipeline)
    device_stats = await device_cursor.to_list(length=None)
    detections_by_device = {stat["_id"]: stat["count"] for stat in device_stats if stat["_id"]}

    return {
      "total_detections": total_detections,
      "detections_by_camera": detections_by_camera,
      "detections_by_device": detections_by_device
    }

  async def setup_indexes(self):
    """Creates necessary indexes for the collection."""
    await self.db[self.collection_name].create_index([("timestamp", DESCENDING)])
    await self.db[self.collection_name].create_index([("camera_id", ASCENDING), ("timestamp", DESCENDING)])
    await self.db[self.collection_name].create_index([("device_id", ASCENDING), ("timestamp", DESCENDING)])

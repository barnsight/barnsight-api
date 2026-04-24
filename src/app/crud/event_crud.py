import inspect
from datetime import datetime
from typing import Optional

from core.schemas.events import EventCreate
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from .base_crud import BaseCRUD


class EventCRUD(BaseCRUD):
  def __init__(self, db: AsyncDatabase):
    super().__init__(db)
    self.collection_name = "events"

  async def _aggregate(self, pipeline: list[dict]):
    cursor = self.db[self.collection_name].aggregate(pipeline)
    if inspect.isawaitable(cursor):
      cursor = await cursor
    return await cursor.to_list(length=None)

  async def create_event(self, event: dict | EventCreate):
    """Create a detection event, deduplicating retried edge submissions by event_id."""
    if hasattr(event, "model_dump"):
      event_dict = event.model_dump()
    else:
      event_dict = event

    if event_dict.get("event_id") and event_dict.get("account_id"):
      existing = await self.db[self.collection_name].find_one(
        {"account_id": event_dict["account_id"], "event_id": event_dict["event_id"]}
      )
      if existing:
        existing["_id"] = str(existing["_id"])
        return existing

    try:
      result = await self.db[self.collection_name].insert_one(event_dict)
      event_dict["_id"] = str(result.inserted_id)
      return event_dict
    except DuplicateKeyError:
      existing = await self.db[self.collection_name].find_one(
        {"account_id": event_dict["account_id"], "event_id": event_dict["event_id"]}
      )
      if existing:
        existing["_id"] = str(existing["_id"])
        return existing
      raise

  async def get_event_by_event_id(self, account_id: str, event_id: str) -> Optional[dict]:
    """Return an event by account-scoped idempotency key."""
    event = await self.db[self.collection_name].find_one(
      {"account_id": account_id, "event_id": event_id}
    )
    if event:
      event["_id"] = str(event["_id"])
    return event

  async def get_events(
    self,
    account_id: str,
    camera_id: Optional[str] = None,
    device_id: Optional[str] = None,
    barn_id: Optional[str] = None,
    zone_id: Optional[str] = None,
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
    if barn_id:
      query["barn_id"] = barn_id
    if zone_id:
      query["zone_id"] = zone_id

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

    cursor_obj = self.db[self.collection_name].find(query).sort("_id", DESCENDING).limit(limit)
    events = await cursor_obj.to_list(length=limit)

    # Convert ObjectId to string for response
    for event in events:
      event["_id"] = str(event["_id"])

    next_cursor = events[-1]["_id"] if events else None
    total = await self.db[self.collection_name].count_documents(query)
    return events, total, next_cursor

  async def get_analytics(
    self,
    account_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    barn_id: Optional[str] = None,
    device_id: Optional[str] = None,
    camera_id: Optional[str] = None,
    zone_id: Optional[str] = None,
  ):
    """Aggregate hygiene analytics scoped by account when provided."""
    match: dict = {}
    if account_id:
      match["account_id"] = account_id
    if start_time or end_time:
      match["timestamp"] = {}
      if start_time:
        match["timestamp"]["$gte"] = start_time
      if end_time:
        match["timestamp"]["$lte"] = end_time
    if barn_id:
      match["barn_id"] = barn_id
    if device_id:
      match["device_id"] = device_id
    if camera_id:
      match["camera_id"] = camera_id
    if zone_id:
      match["zone_id"] = zone_id

    total_detections = await self.db[self.collection_name].count_documents(match)

    async def grouped_counts(field: str) -> dict[str, int]:
      pipeline = [
        {"$match": match},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$sort": {"count": DESCENDING}},
      ]
      stats = await self._aggregate(pipeline)
      return {str(stat["_id"]): stat["count"] for stat in stats if stat["_id"] is not None}

    avg_pipeline = [
      {"$match": match},
      {"$group": {"_id": None, "avg_confidence": {"$avg": "$confidence"}}},
    ]
    avg_results = await self._aggregate(avg_pipeline)
    avg_conf = avg_results[0].get("avg_confidence") if avg_results else None

    hourly_pipeline = [
      {"$match": match},
      {
        "$group": {
          "_id": {"$dateToString": {"format": "%Y-%m-%dT%H:00:00Z", "date": "$timestamp"}},
          "count": {"$sum": 1},
        }
      },
      {"$sort": {"_id": ASCENDING}},
    ]
    hourly_results = await self._aggregate(hourly_pipeline)
    hourly_trends = {r["_id"]: r["count"] for r in hourly_results if r["_id"]}

    daily_pipeline = [
      {"$match": match},
      {
        "$group": {
          "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
          "count": {"$sum": 1},
        }
      },
      {"$sort": {"_id": ASCENDING}},
    ]
    daily_results = await self._aggregate(daily_pipeline)
    daily_trends = {r["_id"]: r["count"] for r in daily_results if r["_id"]}

    high_contamination_periods = [
      {"period": period, "detections": count}
      for period, count in hourly_trends.items()
      if count >= 10
    ]

    backlog_pipeline = [
      {"$match": {**match, "queue_latency_seconds": {"$gt": 0}}},
      {
        "$project": {
          "device_id": 1,
          "timestamp": 1,
          "queue_latency_seconds": 1,
        }
      },
      {"$sort": {"queue_latency_seconds": DESCENDING}},
      {"$limit": 20},
    ]
    backlog_results = await self._aggregate(backlog_pipeline)
    queue_backlog_indicators = [
      {
        "device_id": item.get("device_id"),
        "timestamp": item.get("timestamp"),
        "queue_latency_seconds": item.get("queue_latency_seconds", 0),
      }
      for item in backlog_results
    ]

    return {
      "total_detections": total_detections,
      "average_confidence": round(avg_conf, 2) if avg_conf is not None else 0.0,
      "detections_by_barn": await grouped_counts("barn_id"),
      "detections_by_zone": await grouped_counts("zone_id"),
      "detections_by_camera": await grouped_counts("camera_id"),
      "detections_by_device": await grouped_counts("device_id"),
      "hourly_trends": hourly_trends,
      "daily_trends": daily_trends,
      "high_contamination_periods": high_contamination_periods,
      "queue_backlog_indicators": queue_backlog_indicators,
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
      [("account_id", ASCENDING), ("event_id", ASCENDING)],
      unique=True,
      partialFilterExpression={"event_id": {"$exists": True, "$type": "string"}},
    )
    await self.db[self.collection_name].create_index(
      [("account_id", ASCENDING), ("timestamp", DESCENDING)]
    )
    await self.db[self.collection_name].create_index(
      [("account_id", ASCENDING), ("barn_id", ASCENDING), ("timestamp", DESCENDING)]
    )
    await self.db[self.collection_name].create_index(
      [("account_id", ASCENDING), ("device_id", ASCENDING), ("timestamp", DESCENDING)]
    )
    await self.db[self.collection_name].create_index(
      [("account_id", ASCENDING), ("camera_id", ASCENDING), ("timestamp", DESCENDING)]
    )
    await self.db[self.collection_name].create_index(
      [
        ("account_id", ASCENDING),
        ("barn_id", ASCENDING),
        ("zone_id", ASCENDING),
        ("timestamp", DESCENDING),
      ]
    )

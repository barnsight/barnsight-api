"""Barn, zone, and device CRUD operations for MongoDB."""

from datetime import datetime
from typing import List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

from .base_crud import BaseCRUD


class BarnCRUD(BaseCRUD):
  """CRUD operations for barns, zones, and devices."""

  def __init__(self, db: AsyncDatabase):
    super().__init__(db)
    self.barns_collection = "barns"
    self.zones_collection = "zones"
    self.devices_collection = "devices"

  async def setup_indexes(self):
    """Creates necessary indexes for barn/zone/device collections."""
    await self.db[self.barns_collection].create_index([("barn_id", ASCENDING)], unique=True)
    await self.db[self.zones_collection].create_index(
      [("barn_id", ASCENDING), ("zone_id", ASCENDING)], unique=True
    )
    await self.db[self.devices_collection].create_index(
      [("barn_id", ASCENDING), ("zone_id", ASCENDING), ("camera_id", ASCENDING)], unique=True
    )

  async def get_all_barns(self, account_id: Optional[str] = None) -> List[dict]:
    """Return all barns with their zones and cameras."""
    barns_cursor = self.db[self.barns_collection].find().sort("barn_id", ASCENDING)
    barns = await barns_cursor.to_list(length=None)

    result = []
    for barn in barns:
      barn["_id"] = str(barn["_id"])
      zones = await self.get_zones_for_barn(barn["barn_id"], account_id)
      barn["zones"] = zones
      result.append(barn)

    return result

  async def get_barn_by_id(self, barn_id: int, account_id: Optional[str] = None) -> Optional[dict]:
    """Return a single barn with its zones and cameras."""
    barn = await self.db[self.barns_collection].find_one({"barn_id": barn_id})
    if not barn:
      return None

    barn["_id"] = str(barn["_id"])
    zones = await self.get_zones_for_barn(barn_id, account_id)
    barn["zones"] = zones
    return barn

  async def get_zones_for_barn(self, barn_id: int, account_id: Optional[str] = None) -> List[dict]:
    """Return all zones for a given barn with their cameras."""
    zones_cursor = (
      self.db[self.zones_collection].find({"barn_id": barn_id}).sort("zone_id", ASCENDING)
    )
    zones = await zones_cursor.to_list(length=None)

    result = []
    for zone in zones:
      zone["_id"] = str(zone["_id"])
      cameras = await self.get_cameras_for_zone(barn_id, zone["zone_id"], account_id)
      zone["cameras"] = cameras
      result.append(zone)

    return result

  async def get_cameras_for_zone(
    self, barn_id: int, zone_id: int, account_id: Optional[str] = None
  ) -> List[dict]:
    """Return all cameras for a given barn and zone, with online status from Redis."""
    from core.database import RedisClient

    cameras_cursor = (
      self.db[self.devices_collection]
      .find({"barn_id": barn_id, "zone_id": zone_id})
      .sort("camera_id", ASCENDING)
    )
    cameras = await cameras_cursor.to_list(length=None)

    redis = RedisClient()
    for cam in cameras:
      cam["_id"] = str(cam["_id"])

      # Determine device status from Redis heartbeat
      # If account_id is not provided, we might not be able to construct the key accurately
      # but let's assume we can find it if we have it.
      if account_id:
        device_id = cam.get("camera_id")  # Assuming camera_id is used as device_id
        status_key = f"device:{account_id}:{device_id}:status"
        is_online = await redis.get(status_key)
        cam["status"] = "online" if is_online else "offline"

    return cameras

  async def get_barn_ids_for_user(self, username: str, role: str) -> Optional[List[int]]:
    """Return assigned barn IDs for a non-admin user. Returns None for admin (all barns)."""
    if role == "admins":
      return None

    user_barns = await self.db["user_barns"].find_one({"username": username})
    if user_barns and "barn_ids" in user_barns:
      return user_barns["barn_ids"]

    return None

  async def get_detections_by_date(
    self,
    start: datetime,
    end: datetime,
    barn_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    device_id: Optional[str] = None,
    account_id: Optional[str] = None,
  ) -> List[dict]:
    """Fetch detections grouped by event for the given date range and filters."""
    events_db = self.db.client.get_database("barnsight")
    query: dict = {"timestamp": {"$gte": start, "$lte": end}}

    if account_id:
      query["account_id"] = account_id
    if device_id:
      query["device_id"] = device_id

    pipeline = [
      {"$match": query},
      {"$sort": {"timestamp": ASCENDING}},
      {
        "$group": {
          "_id": "$_id",
          "timestamp": {"$first": "$timestamp"},
          "camera_id": {"$first": "$camera_id"},
          "device_id": {"$first": "$device_id"},
          "confidence": {"$first": "$confidence"},
          "bounding_box": {"$first": "$bounding_box"},
        }
      },
      {"$sort": {"timestamp": ASCENDING}},
    ]

    cursor = events_db["events"].aggregate(pipeline)
    events = await cursor.to_list(length=None)

    result = []
    for idx, event in enumerate(events):
      bbox = event.get("bounding_box", {})
      detection_item = {
        "bbox": [bbox.get("x", 0), bbox.get("y", 0), bbox.get("width", 0), bbox.get("height", 0)],
        "confidence": event.get("confidence", 0),
        "type": "excrement",
      }

      result.append(
        {
          "id": idx + 1,
          "timestamp": event["timestamp"],
          "zone_id": zone_id or 0,
          "device_id": event.get("device_id", ""),
          "detections": [detection_item],
        }
      )

    return result

  async def get_report_by_date(
    self,
    start: datetime,
    end: datetime,
    barn_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    account_id: Optional[str] = None,
  ) -> dict:
    """Generate a report summary for the given date range."""
    events_db = self.db.client.get_database("barnsight")
    query: dict = {"timestamp": {"$gte": start, "$lte": end}}

    if account_id:
      query["account_id"] = account_id

    total_detections = await events_db["events"].count_documents(query)

    daily_pipeline = [
      {"$match": query},
      {
        "$group": {
          "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
          "count": {"$sum": 1},
        }
      },
      {"$sort": {"_id": ASCENDING}},
    ]

    daily_cursor = await events_db["events"].aggregate(daily_pipeline)
    daily_results = await daily_cursor.to_list(length=None)
    daily_summary = [{"date": d["_id"], "detections": d["count"]} for d in daily_results]

    zone_pipeline = [
      {"$match": query},
      {"$group": {"_id": "$camera_id", "count": {"$sum": 1}}},
      {"$sort": {"count": DESCENDING}},
    ]

    zone_cursor = await events_db["events"].aggregate(zone_pipeline)
    zone_results = await zone_cursor.to_list(length=None)
    high_risk_count = max(1, len(zone_results) // 3)
    high_risk_zones = [f"Zone {r['_id']}" for r in zone_results[:high_risk_count]]

    if len(daily_summary) >= 2:
      first_half = sum(d["detections"] for d in daily_summary[: len(daily_summary) // 2])
      second_half = sum(d["detections"] for d in daily_summary[len(daily_summary) // 2 :])
      if second_half < first_half * 0.9:
        trend = "improving"
      elif second_half > first_half * 1.1:
        trend = "worsening"
      else:
        trend = "stable"
    else:
      trend = "stable"

    return {
      "barn_id": barn_id,
      "start_date": start.strftime("%Y-%m-%d"),
      "end_date": end.strftime("%Y-%m-%d"),
      "total_detections": total_detections,
      "high_risk_zones": high_risk_zones,
      "trend": trend,
      "daily_summary": daily_summary,
    }

  async def get_analytics_by_date(
    self,
    start: datetime,
    end: datetime,
    barn_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    account_id: Optional[str] = None,
  ) -> dict:
    """Generate analytics for the given date range."""
    events_db = self.db.client.get_database("barnsight")
    query: dict = {"timestamp": {"$gte": start, "$lte": end}}

    if account_id:
      query["account_id"] = account_id

    total_detections = await events_db["events"].count_documents(query)

    avg_pipeline = [
      {"$match": query},
      {"$group": {"_id": None, "avg_confidence": {"$avg": "$confidence"}}},
    ]
    avg_cursor = await events_db["events"].aggregate(avg_pipeline)
    avg_results = await avg_cursor.to_list(length=None)
    avg_conf = avg_results[0].get("avg_confidence") if avg_results else None
    average_confidence = round(avg_conf, 2) if avg_conf is not None else 0.0

    barn_pipeline = [
      {"$match": query},
      {"$group": {"_id": "$account_id", "count": {"$sum": 1}}},
    ]
    barn_cursor = await events_db["events"].aggregate(barn_pipeline)
    barn_results = await barn_cursor.to_list(length=None)
    detections_per_barn = {f"Barn {r['_id']}": r["count"] for r in barn_results if r["_id"]}

    if len(barn_results) >= 2:
      counts = [r["count"] for r in barn_results]
      avg_count = sum(counts) / len(counts)
      variance = sum((c - avg_count) ** 2 for c in counts) / len(counts)
      if variance < avg_count * 0.5:
        trend = "stable"
      else:
        trend = "variable"
    else:
      trend = "stable"

    return {
      "start_date": start.strftime("%Y-%m-%d"),
      "end_date": end.strftime("%Y-%m-%d"),
      "total_detections": total_detections,
      "average_confidence": average_confidence,
      "detections_per_barn": detections_per_barn,
      "trend": trend,
    }

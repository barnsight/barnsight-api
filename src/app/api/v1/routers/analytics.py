"""Analytics routes for aggregated detection insights.

Requires JWT authentication and scopes results to the account.
"""

from datetime import date, datetime
from typing import Annotated, Optional

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.events import AnalyticsSummaryResponse
from crud.event_crud import EventCRUD
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(tags=["Analytics"])


@router.get(
  "",
  status_code=status.HTTP_200_OK,
  response_model=AnalyticsSummaryResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_analytics(
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  user: Annotated[dict, Depends(get_current_user)],
  start: Optional[date] = Query(None, description="Start date"),
  end: Optional[date] = Query(None, description="End date"),
  barn_id: Optional[int] = Query(None, description="Filter by barn ID"),
  device_id: Optional[str] = Query(None, description="Filter by device ID"),
  camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
  zone_id: Optional[int] = Query(None, description="Filter by zone ID"),
):
  """Return aggregated detection analytics scoped to the authenticated account."""
  role = user.get("role", "")
  username = user.get("username")
  account_id = username if role != "admins" else None
  start_dt = datetime(start.year, start.month, start.day, 0, 0, 0) if start else None
  end_dt = datetime(end.year, end.month, end.day, 23, 59, 59) if end else None

  events_db = mongo.get_database("barnsight")
  event_crud = EventCRUD(events_db)
  analytics_data = await event_crud.get_analytics(
    account_id=account_id,
    start_time=start_dt,
    end_time=end_dt,
    barn_id=str(barn_id) if barn_id is not None else None,
    device_id=device_id,
    camera_id=camera_id,
    zone_id=str(zone_id) if zone_id is not None else None,
  )

  device_query = {} if account_id is None else {"account_id": account_id}
  device_cursor = events_db["device_heartbeats"].find(device_query)
  devices = await device_cursor.to_list(length=None)
  offline_periods = [
    {
      "device_id": device.get("device_id"),
      "last_heartbeat_at": device.get("last_heartbeat_at"),
      "status": "offline",
    }
    for device in devices
    if device.get("status") == "offline"
  ]

  trend = "stable"
  daily_counts = list(analytics_data.get("daily_trends", {}).values())
  if len(daily_counts) >= 2:
    trend = "worsening" if daily_counts[-1] > daily_counts[0] else "improving"

  analytics_data = {
    "start_date": start.isoformat() if start else "N/A",
    "end_date": end.isoformat() if end else "N/A",
    "total_detections": analytics_data.get("total_detections", 0),
    "average_confidence": analytics_data.get("average_confidence", 0.0),
    "detections_per_barn": analytics_data.get("detections_by_barn", {}),
    "detections_per_zone": analytics_data.get("detections_by_zone", {}),
    "detections_per_camera": analytics_data.get("detections_by_camera", {}),
    "detections_per_device": analytics_data.get("detections_by_device", {}),
    "hourly_trends": analytics_data.get("hourly_trends", {}),
    "daily_trends": analytics_data.get("daily_trends", {}),
    "high_contamination_periods": analytics_data.get("high_contamination_periods", []),
    "device_offline_periods": offline_periods,
    "queue_backlog_indicators": analytics_data.get("queue_backlog_indicators", []),
    "trend": trend,
  }

  return analytics_data

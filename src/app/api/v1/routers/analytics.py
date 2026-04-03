"""Analytics routes for aggregated detection insights.

Requires JWT authentication and scopes results to the account.
"""

from datetime import date, datetime
from typing import Annotated, Optional

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.barns import AnalyticsByDateResponse
from crud.barn_crud import BarnCRUD
from crud.event_crud import EventCRUD
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(tags=["Analytics"])


@router.get(
  "",
  status_code=status.HTTP_200_OK,
  response_model=AnalyticsByDateResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_analytics(
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  user: Annotated[dict, Depends(get_current_user)],
  start: Optional[date] = Query(None, description="Start date"),
  end: Optional[date] = Query(None, description="End date"),
  barn_id: Optional[int] = Query(None, description="Filter by barn ID"),
  zone_id: Optional[int] = Query(None, description="Filter by zone ID"),
):
  """Return aggregated detection analytics scoped to the authenticated account."""
  db = mongo.get_database("barnsight")
  barn_crud = BarnCRUD(db)

  role = user.get("role", "")
  username = user.get("username")

  if start and end:
    start_dt = datetime(start.year, start.month, start.day, 0, 0, 0)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)
    account_id = username if role != "admins" else None

    analytics_data = await barn_crud.get_analytics_by_date(
      start=start_dt,
      end=end_dt,
      barn_id=barn_id,
      zone_id=zone_id,
      account_id=account_id,
    )
  else:
    events_db = mongo.get_database("barnsight")
    event_crud = EventCRUD(events_db)
    analytics_data = await event_crud.get_analytics()
    analytics_data = {
      "start_date": "N/A",
      "end_date": "N/A",
      "total_detections": analytics_data.get("total_detections", 0),
      "average_confidence": 0.0,
      "detections_per_barn": analytics_data.get("detections_by_camera", {}),
      "trend": "stable",
    }

  return analytics_data

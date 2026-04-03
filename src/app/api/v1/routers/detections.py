"""Detections by date routes.

Handles querying detection events with date range and optional filters.
"""

from datetime import date, datetime
from typing import Annotated, Optional

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.barns import DetectionsByDateResponse
from crud.barn_crud import BarnCRUD
from fastapi import APIRouter, Depends, HTTPException, Query, status

router = APIRouter(tags=["Detections"])


@router.get(
  "",
  status_code=status.HTTP_200_OK,
  response_model=DetectionsByDateResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_detections_by_date(
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  start: date = Query(..., description="Start date, e.g., 2026-04-01"),
  end: date = Query(..., description="End date, e.g., 2026-04-03"),
  barn_id: Optional[int] = Query(None, description="Filter by barn ID"),
  zone_id: Optional[int] = Query(None, description="Filter by zone ID"),
  device_id: Optional[str] = Query(None, description="Filter by device ID"),
):
  """Return detections between start and end dates with optional filters."""
  db = mongo.get_database("barnsight")
  barn_crud = BarnCRUD(db)

  role = user.get("role", "")
  username = user.get("username")
  barn_ids = await barn_crud.get_barn_ids_for_user(username, role)

  if barn_ids is not None and barn_id is not None and barn_id not in barn_ids:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Access denied to this barn.",
    )

  start_dt = datetime(start.year, start.month, start.day, 0, 0, 0)
  end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)

  account_id = username if role != "admins" else None

  detections = await barn_crud.get_detections_by_date(
    start=start_dt,
    end=end_dt,
    barn_id=barn_id,
    zone_id=zone_id,
    device_id=device_id,
    account_id=account_id,
  )

  return {
    "barn_id": barn_id,
    "start_date": start.isoformat(),
    "end_date": end.isoformat(),
    "detections": detections,
  }

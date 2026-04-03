"""Custom reports by date routes.

Handles generating hygiene reports with date range and optional filters.
"""

from datetime import date, datetime
from typing import Annotated, Optional

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.barns import ReportByDateResponse
from crud.barn_crud import BarnCRUD
from fastapi import APIRouter, Depends, HTTPException, Query, status

router = APIRouter(tags=["Reports"])


@router.get(
  "/custom",
  status_code=status.HTTP_200_OK,
  response_model=ReportByDateResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_report_by_date(
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  start: date = Query(..., description="Start date"),
  end: date = Query(..., description="End date"),
  barn_id: Optional[int] = Query(None, description="Filter by barn ID"),
  zone_id: Optional[int] = Query(None, description="Filter by zone ID"),
):
  """Return a custom report summary between start and end dates."""
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

  report = await barn_crud.get_report_by_date(
    start=start_dt,
    end=end_dt,
    barn_id=barn_id,
    zone_id=zone_id,
    account_id=account_id,
  )

  return report

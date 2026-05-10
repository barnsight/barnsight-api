"""Custom reports by date routes.

Handles generating hygiene reports with date range and optional filters.
"""

from datetime import date, datetime
from typing import Annotated, Optional

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from bson import ObjectId
from core.database import MongoClient
from core.permissions import account_id_from_user, farm_id_from_user, scoped_query
from core.schemas.barns import ReportByDateResponse
from core.schemas.platform import ReportGenerateRequest
from crud.barn_crud import BarnCRUD
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["Reports"])


def _serialize(doc: dict) -> dict:
  doc["_id"] = str(doc["_id"])
  return doc


@router.get("", dependencies=[Depends(limit_dependency)])
async def list_reports(
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  cursor = db["reports"].find(scoped_query(user)).sort("created_at", -1)
  reports = await cursor.to_list(length=100)
  return {"reports": [_serialize(report) for report in reports]}


@router.post(
  "/generate", status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit_dependency)]
)
async def generate_report(
  body: ReportGenerateRequest,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  report = {
    "account_id": account_id_from_user(user),
    "farm_id": farm_id_from_user(user),
    "name": f"Hygiene report {body.start_date.date()} to {body.end_date.date()}",
    "filters": body.model_dump(mode="json"),
    "status": "ready",
    "format": body.format,
    "created_at": datetime.utcnow(),
  }
  result = await db["reports"].insert_one(report)
  report["_id"] = str(result.inserted_id)
  return report


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


@router.get("/{report_id}", dependencies=[Depends(limit_dependency)])
async def get_report(
  report_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  try:
    object_id = ObjectId(report_id)
  except Exception as exc:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found") from exc
  report = await db["reports"].find_one(scoped_query(user, {"_id": object_id}))
  if not report:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
  return _serialize(report)


@router.delete(
  "/{report_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def delete_report(
  report_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  try:
    object_id = ObjectId(report_id)
  except Exception as exc:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found") from exc
  result = await db["reports"].delete_one(scoped_query(user, {"_id": object_id}))
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
  return None


@router.get("/{report_id}/download", dependencies=[Depends(limit_dependency)])
async def download_report(
  report_id: str,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  report = await get_report(report_id=report_id, user=user, mongo=mongo)
  return PlainTextResponse(str(report), media_type="text/plain")

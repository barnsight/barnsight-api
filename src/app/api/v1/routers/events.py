"""Event ingestion and query routes.

Handles detection event submission from edge devices (API key)
or web users (JWT), and event querying with filtering.
"""

from typing import Annotated, Optional
from datetime import datetime

from fastapi import APIRouter, status, Depends, Query, HTTPException, Request

from core.schemas.events import EventCreate, EventResponse, EventListResponse
from core.database import MongoClient
from api.dependencies import get_mongo_client, limit_dependency, get_jwt_payload
from api.auth_dependencies import validate_api_key
from crud.event_crud import EventCRUD
from core.services.cloudinary_service import upload_base64_image

router = APIRouter(tags=["Events"])


async def get_event_owner(
  request: Request,
  api_key_data: Annotated[Optional[dict], Depends(validate_api_key)],
):
  """Determine the account owner from API key or JWT.

  Accepts either an edge device API key or a web user JWT.
  """
  if api_key_data:
    return api_key_data.get("owner_id")

  payload = get_jwt_payload(request)
  if payload:
    return payload.get("sub")

  raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Missing authentication (API Key or JWT)",
  )


@router.post(
  "",
  status_code=status.HTTP_201_CREATED,
  response_model=EventResponse,
  dependencies=[Depends(limit_dependency)],
)
async def create_event(
  event: EventCreate,
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Submit a detection event.

  Uploads base64 image snapshots to Cloudinary if provided.
  Associates the event with the authenticated account.
  """
  events_db = mongo.get_database("barnsight")
  event_crud = EventCRUD(events_db)

  event_dict = event.model_dump()
  event_dict["account_id"] = owner_id

  # Upload image to Cloudinary if provided
  if event.image_snapshot:
    folder = f"barnsight/manure/{owner_id}"
    secure_url = await upload_base64_image(event.image_snapshot, folder=folder)
    event_dict["image_snapshot"] = secure_url

  result = await event_crud.create_event(event_dict)
  event_dict["_id"] = str(result.inserted_id)
  return event_dict


@router.get(
  "",
  status_code=status.HTTP_200_OK,
  response_model=EventListResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_events(
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
  device_id: Optional[str] = Query(None, description="Filter by device ID"),
  start_time: Optional[datetime] = Query(None, description="Filter events after this UTC time"),
  end_time: Optional[datetime] = Query(None, description="Filter events before this UTC time"),
  offset: int = Query(0, ge=0, description="Pagination offset"),
  limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
):
  """Query events belonging to the authenticated account."""
  events_db = mongo.get_database("barnsight")
  event_crud = EventCRUD(events_db)

  query = {"account_id": owner_id}
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

  cursor = events_db["events"].find(query).sort("timestamp", -1).skip(offset).limit(limit)
  events = await cursor.to_list(length=limit)
  for e in events:
    e["_id"] = str(e["_id"])
  total = await events_db["events"].count_documents(query)

  return {"events": events, "total": total}

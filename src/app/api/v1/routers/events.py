"""Event ingestion and query routes.

Handles detection event submission from edge devices (API key)
or web users (JWT), and event querying with filtering.
"""

from datetime import datetime
from typing import Annotated, Optional

import json
from api.auth_dependencies import validate_api_key
from api.dependencies import get_jwt_payload, get_mongo_client, limit_dependency
from core.config import settings
from core.database import MongoClient, RedisClient
from core.schemas.events import EventCreate, EventListResponse, EventResponse
from core.services.cloudinary_service import upload_base64_image
from crud.event_crud import EventCRUD
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer

router = APIRouter(tags=["Events"])

optional_oauth2_scheme = OAuth2PasswordBearer(
  tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False
)


async def get_event_owner(
  request: Request,
  api_key_data: Annotated[Optional[dict], Depends(validate_api_key)],
  token: Annotated[Optional[str], Depends(optional_oauth2_scheme)],
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
  background_tasks: BackgroundTasks,
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

  # Publish to Redis for Real-Time WebSockets
  redis = RedisClient()
  channel = f"account:{owner_id}:events"
  await redis.publish(channel, json.dumps(result, default=str))

  # Trigger alerting background task if confidence is high
  if result.get("confidence", 0) > 0.8:
    from core.services.alert_service import check_and_send_alert
    background_tasks.add_task(check_and_send_alert, owner_id, result)

  return result


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
  cursor: Optional[str] = Query(None, description="Pagination cursor (event _id)"),
  limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
):
  """Query events belonging to the authenticated account."""
  events_db = mongo.get_database("barnsight")
  event_crud = EventCRUD(events_db)

  events, total, next_cursor = await event_crud.get_events(
    account_id=owner_id,
    camera_id=camera_id,
    device_id=device_id,
    start_time=start_time,
    end_time=end_time,
    cursor=cursor,
    limit=limit,
  )

  return {"events": events, "total": total, "next_cursor": next_cursor}

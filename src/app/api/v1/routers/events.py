"""Event ingestion and query routes.

Handles detection event submission from edge devices (API key)
or web users (JWT), and event querying with filtering.
"""

import json
from datetime import datetime
from typing import Annotated, Optional

from api.auth_dependencies import validate_api_key
from api.dependencies import get_jwt_payload, get_mongo_client, get_redis_client, limit_dependency
from bson import ObjectId
from core.config import settings
from core.database import MongoClient, RedisClient
from core.schemas.events import EventCreate, EventListResponse, EventResponse
from core.schemas.platform import (
  EventNoteCreate,
  EventReviewUpdate,
  EventStatusUpdate,
  GenericPatch,
)
from core.services.audit_service import write_audit_log
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
  redis: Annotated[RedisClient, Depends(get_redis_client)],
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

  if event.event_id:
    existing = await event_crud.get_event_by_event_id(owner_id, event.event_id)
    if existing:
      return existing

  # Upload image to Cloudinary if provided
  if event.image_snapshot:
    folder = f"barnsight/manure/{owner_id}"
    secure_url = await upload_base64_image(event.image_snapshot, folder=folder)
    event_dict["image_snapshot"] = secure_url

  result = await event_crud.create_event(event_dict)

  # Publish to Redis for Real-Time WebSockets
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
  barn_id: Optional[str] = Query(None, description="Filter by barn ID"),
  zone_id: Optional[str] = Query(None, description="Filter by zone ID"),
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
    barn_id=barn_id,
    zone_id=zone_id,
    start_time=start_time,
    end_time=end_time,
    cursor=cursor,
    limit=limit,
  )

  return {"events": events, "total": total, "next_cursor": next_cursor}


def _event_lookup(owner_id: str, event_id: str) -> dict:
  lookup: dict = {"account_id": owner_id}
  try:
    lookup["_id"] = ObjectId(event_id)
  except Exception:
    lookup["event_id"] = event_id
  return lookup


@router.get(
  "/{event_id}",
  status_code=status.HTTP_200_OK,
  response_model=EventResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_event(
  event_id: str,
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  event = await db["events"].find_one(_event_lookup(owner_id, event_id))
  if not event:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
  event["_id"] = str(event["_id"])
  return event


@router.patch("/{event_id}", dependencies=[Depends(limit_dependency)])
async def update_event(
  event_id: str,
  update: GenericPatch,
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  data = update.model_dump(exclude_unset=True)
  data.pop("account_id", None)
  data.pop("farm_id", None)
  data.pop("device_id", None)
  if not data:
    return {"message": "No fields to update."}
  result = await db["events"].update_one(_event_lookup(owner_id, event_id), {"$set": data})
  if result.modified_count == 0:
    existing = await db["events"].find_one(_event_lookup(owner_id, event_id))
    if not existing:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
  saved = await db["events"].find_one(_event_lookup(owner_id, event_id))
  saved["_id"] = str(saved["_id"])
  return saved


@router.delete(
  "/{event_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def delete_event(
  event_id: str,
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  result = await db["events"].delete_one(_event_lookup(owner_id, event_id))
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
  return


@router.patch("/{event_id}/review", dependencies=[Depends(limit_dependency)])
async def review_event(
  event_id: str,
  review: EventReviewUpdate,
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  event = await db["events"].find_one(_event_lookup(owner_id, event_id))
  if not event:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
  review_doc = {
    "event_id": str(event["_id"]),
    "account_id": owner_id,
    "status": review.status,
    "note": review.note,
    "reviewed_at": datetime.utcnow(),
  }
  await db["event_reviews"].insert_one(review_doc)
  await db["events"].update_one({"_id": event["_id"]}, {"$set": {"status": review.status}})
  await write_audit_log(
    db,
    action="event.reviewed",
    account_id=owner_id,
    resource_type="event",
    resource_id=str(event["_id"]),
    metadata={"status": review.status},
  )
  return {"message": "Event reviewed.", "status": review.status}


@router.patch("/{event_id}/status", dependencies=[Depends(limit_dependency)])
async def update_event_status(
  event_id: str,
  body: EventStatusUpdate,
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  event = await db["events"].find_one(_event_lookup(owner_id, event_id))
  if not event:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
  await db["events"].update_one({"_id": event["_id"]}, {"$set": {"status": body.status}})
  await write_audit_log(
    db,
    action="event.status_changed",
    account_id=owner_id,
    resource_type="event",
    resource_id=str(event["_id"]),
    metadata={"status": body.status},
  )
  return {"message": "Event status updated.", "status": body.status}


@router.post(
  "/{event_id}/notes",
  status_code=status.HTTP_201_CREATED,
  dependencies=[Depends(limit_dependency)],
)
async def add_event_note(
  event_id: str,
  body: EventNoteCreate,
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  event = await db["events"].find_one(_event_lookup(owner_id, event_id))
  if not event:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
  note = {
    "event_id": str(event["_id"]),
    "account_id": owner_id,
    "note": body.note,
    "created_at": datetime.utcnow(),
  }
  result = await db["event_notes"].insert_one(note)
  note["_id"] = str(result.inserted_id)
  return note


@router.get("/{event_id}/snapshot", dependencies=[Depends(limit_dependency)])
async def get_event_snapshot(
  event_id: str,
  owner_id: Annotated[str, Depends(get_event_owner)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("barnsight")
  event = await db["events"].find_one(_event_lookup(owner_id, event_id))
  if not event:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
  return {"snapshot": event.get("image_snapshot"), "event_id": str(event["_id"])}

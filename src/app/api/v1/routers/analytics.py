from typing import Annotated
from fastapi import (
  APIRouter,
  status,
  Depends
)
from core.schemas.events import AnalyticsResponse
from core.database import MongoClient
from api.dependencies import get_mongo_client, limit_dependency
from crud.event_crud import EventCRUD

router = APIRouter(tags=["Analytics"])

@router.get("",
  status_code=status.HTTP_200_OK,
  response_model=AnalyticsResponse,
  dependencies=[Depends(limit_dependency)])
async def get_analytics(
  mongo: Annotated[MongoClient, Depends(get_mongo_client)]
):
  """
  Provide aggregated insights of detection events.
  """
  events_db = mongo.get_database("events")
  event_crud = EventCRUD(events_db)
  
  analytics_data = await event_crud.get_analytics()
  
  return analytics_data

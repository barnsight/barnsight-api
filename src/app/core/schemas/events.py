from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
  x: float = Field(..., description="X coordinate of the bounding box")
  y: float = Field(..., description="Y coordinate of the bounding box")
  width: float = Field(..., description="Width of the bounding box")
  height: float = Field(..., description="Height of the bounding box")


class EventCreate(BaseModel):
  timestamp: datetime = Field(..., description="UTC timestamp of the detection")
  camera_id: str = Field(..., description="Identifier for the camera")
  device_id: Optional[str] = Field(None, description="Identifier for the edge device")
  confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score of the detection")
  bounding_box: BoundingBox
  image_snapshot: Optional[str] = Field(None, description="Base64 encoded image snapshot")


class EventResponse(EventCreate):
  id: str = Field(..., alias="_id", description="Event ID")

  class Config:
    populate_by_name = True


class EventListResponse(BaseModel):
  events: List[EventResponse]
  total: int
  next_cursor: Optional[str] = None


class AnalyticsResponse(BaseModel):
  total_detections: int
  detections_by_camera: dict[str, int]
  detections_by_device: dict[str, int]

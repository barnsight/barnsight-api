import base64
import binascii
from datetime import datetime
from typing import Any, List, Literal, Optional

from core.config import settings
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BoundingBox(BaseModel):
  x: float = Field(..., description="X coordinate of the bounding box")
  y: float = Field(..., description="Y coordinate of the bounding box")
  width: float = Field(..., gt=0, description="Width of the bounding box")
  height: float = Field(..., gt=0, description="Height of the bounding box")


class EventBase(BaseModel):
  model_config = ConfigDict(extra="forbid")

  timestamp: datetime = Field(..., description="UTC timestamp of the detection")
  camera_id: str = Field(..., description="Identifier for the camera")
  device_id: str = Field(..., description="Identifier for the physical edge device")
  detected_class: Optional[str] = Field(None, min_length=1, max_length=80)
  confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score of the detection")
  bounding_box: BoundingBox
  image_snapshot: Optional[str] = Field(None, description="Base64 encoded image snapshot")
  model_version: Optional[str] = None
  model_path: Optional[str] = None
  inference_fps: Optional[float] = Field(None, ge=0)
  edge_queue_size: Optional[int] = Field(None, ge=0)
  img_size: Optional[int] = Field(None, gt=0)
  threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
  event_id: Optional[str] = Field(None, min_length=1, max_length=128)
  zone_id: Optional[str] = Field(None, min_length=1, max_length=128)
  barn_id: Optional[str] = Field(None, min_length=1, max_length=128)
  snapshot_mode: Optional[Literal["none", "on_detection", "always", "throttled"]] = None
  edge_app_version: Optional[str] = None
  queue_latency_seconds: Optional[float] = Field(None, ge=0)


class EventCreate(EventBase):
  image_snapshot: Optional[str] = Field(None, description="Base64 encoded image snapshot")

  @field_validator("image_snapshot")
  @classmethod
  def validate_snapshot_size(cls, value: Optional[str]) -> Optional[str]:
    """Reject oversized base64 images before upload or persistence."""
    if value is None:
      return value

    payload = value
    lowered = payload.lower()
    if lowered.startswith("data:"):
      header = lowered.split(",", 1)[0]
      allowed_headers = {
        "data:image/jpeg;base64",
        "data:image/png;base64",
        "data:image/webp;base64",
      }
      if header not in allowed_headers:
        raise ValueError("image_snapshot must be image/jpeg, image/png, or image/webp")
      payload = payload.split(",", 1)[1]

    try:
      decoded_size = len(base64.b64decode(payload, validate=True))
    except (binascii.Error, ValueError) as exc:
      raise ValueError("image_snapshot must be valid base64") from exc

    if decoded_size > settings.EDGE_MAX_SNAPSHOT_BYTES:
      raise ValueError(
        f"image_snapshot exceeds max decoded size of {settings.EDGE_MAX_SNAPSHOT_BYTES} bytes"
      )
    return value


class EventResponse(EventBase):
  image_snapshot: Optional[str] = Field(
    None, description="Stored image snapshot reference, usually a Cloudinary URL"
  )
  id: str = Field(..., alias="_id", description="Event ID")

  model_config = ConfigDict(populate_by_name=True, extra="allow")


class EventListResponse(BaseModel):
  events: List[EventResponse]
  total: int
  next_cursor: Optional[str] = None


class AnalyticsResponse(BaseModel):
  total_detections: int
  detections_by_camera: dict[str, int]
  detections_by_device: dict[str, int]


class AnalyticsSummaryResponse(BaseModel):
  start_date: str
  end_date: str
  total_detections: int
  average_confidence: float
  detections_per_barn: dict[str, int]
  detections_per_zone: dict[str, int]
  detections_per_camera: dict[str, int]
  detections_per_device: dict[str, int]
  hourly_trends: dict[str, int]
  daily_trends: dict[str, int]
  high_contamination_periods: list[dict[str, Any]]
  device_offline_periods: list[dict[str, Any]]
  queue_backlog_indicators: list[dict[str, Any]]
  trend: str

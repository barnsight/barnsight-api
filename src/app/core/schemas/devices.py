"""Schemas for edge device heartbeat, configuration, and detection zones."""

from datetime import datetime
from typing import Any, Literal, Optional

from core.config import settings
from pydantic import BaseModel, ConfigDict, Field


class DeviceHeartbeat(BaseModel):
  model_config = ConfigDict(extra="forbid")

  device_id: str = Field(..., min_length=1, max_length=128)
  camera_id: str = Field(..., min_length=1, max_length=128)
  barn_id: Optional[str] = Field(None, min_length=1, max_length=128)
  status: Literal["online", "degraded", "offline", "error"] = "online"
  edge_app_version: Optional[str] = None
  model_version: Optional[str] = None
  model_path: Optional[str] = None
  camera_connected: Optional[bool] = None
  model_loaded: Optional[bool] = None
  last_frame_at: Optional[datetime] = None
  last_detection_at: Optional[datetime] = None
  fps: Optional[float] = Field(None, ge=0)
  inference_fps: Optional[float] = Field(None, ge=0)
  queue_size: Optional[int] = Field(None, ge=0)
  queue_max_size: Optional[int] = Field(None, ge=1)
  queue_dropped_count: Optional[int] = Field(None, ge=0)
  memory_used_mb: Optional[float] = Field(None, ge=0)
  disk_free_mb: Optional[float] = Field(None, ge=0)
  temperature_c: Optional[float] = None
  uptime_seconds: Optional[float] = Field(None, ge=0)
  errors: list[str] = Field(default_factory=list)


class DeviceCreate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  device_id: str = Field(..., min_length=1, max_length=128)
  barn_id: str = Field(..., min_length=1, max_length=128)
  name: Optional[str] = Field(None, max_length=200)
  location: Optional[str] = Field(None, max_length=200)
  status: Literal["online", "degraded", "offline", "error"] = "offline"


class DeviceUpdate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  barn_id: Optional[str] = Field(None, min_length=1, max_length=128)
  name: Optional[str] = Field(None, max_length=200)
  location: Optional[str] = Field(None, max_length=200)
  status: Optional[Literal["online", "degraded", "offline", "error"]] = None


class DeviceResponse(BaseModel):
  id: Optional[str] = Field(None, alias="_id")
  account_id: str
  device_id: str
  barn_id: str
  name: Optional[str] = None
  location: Optional[str] = None
  status: str
  last_seen_at: Optional[datetime] = None
  created_at: datetime
  updated_at: datetime
  online: bool

  model_config = ConfigDict(populate_by_name=True, extra="allow")


class CameraCreate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  camera_id: str = Field(..., min_length=1, max_length=128)
  device_id: str = Field(..., min_length=1, max_length=128)
  barn_id: str = Field(..., min_length=1, max_length=128)
  name: Optional[str] = Field(None, max_length=200)
  stream_label: Optional[str] = Field(None, max_length=200)
  status: Literal["online", "degraded", "offline", "error"] = "offline"


class CameraUpdate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  device_id: Optional[str] = Field(None, min_length=1, max_length=128)
  barn_id: Optional[str] = Field(None, min_length=1, max_length=128)
  name: Optional[str] = Field(None, max_length=200)
  stream_label: Optional[str] = Field(None, max_length=200)
  status: Optional[Literal["online", "degraded", "offline", "error"]] = None


class CameraResponse(BaseModel):
  id: Optional[str] = Field(None, alias="_id")
  account_id: str
  camera_id: str
  device_id: str
  barn_id: str
  name: Optional[str] = None
  stream_label: Optional[str] = None
  status: str
  last_seen_at: Optional[datetime] = None
  created_at: datetime
  updated_at: datetime
  online: bool

  model_config = ConfigDict(populate_by_name=True, extra="allow")


class DeviceStatusResponse(BaseModel):
  device_id: str
  status: str
  online: bool
  last_seen_at: Optional[datetime] = None
  heartbeat_ttl_seconds: int = settings.DEVICE_HEARTBEAT_TTL_SECONDS


class CameraStatusResponse(BaseModel):
  camera_id: str
  device_id: Optional[str] = None
  status: str
  online: bool
  last_seen_at: Optional[datetime] = None
  heartbeat_ttl_seconds: int = settings.DEVICE_HEARTBEAT_TTL_SECONDS


class DeviceConfig(BaseModel):
  model_config = ConfigDict(extra="forbid")

  enabled: bool = True
  inference_fps: float = Field(2.0, gt=0, le=60)
  img_size: int = Field(640, gt=0, le=4096)
  min_confidence: float = Field(0.5, ge=0, le=1)
  cooldown_seconds: float = Field(10.0, ge=0)
  image_cooldown_seconds: float = Field(60.0, ge=0)
  region_overlap_threshold: float = Field(0.3, ge=0, le=1)
  jpeg_quality: int = Field(85, ge=1, le=100)
  send_image_snapshot: bool = True
  snapshot_mode: Literal["none", "on_detection", "always", "throttled"] = "on_detection"
  max_image_bytes: int = Field(settings.EDGE_MAX_SNAPSHOT_BYTES, gt=0, le=10_000_000)
  detection_zones: list[str] = Field(default_factory=list)
  updated_at: Optional[datetime] = None


class DeviceConfigResponse(DeviceConfig):
  id: Optional[str] = Field(None, alias="_id")
  account_id: str
  device_id: str
  updated_at: datetime

  model_config = ConfigDict(populate_by_name=True, extra="allow")


class PolygonPoint(BaseModel):
  x: float = Field(..., ge=0, le=1)
  y: float = Field(..., ge=0, le=1)


class DetectionZoneBase(BaseModel):
  model_config = ConfigDict(extra="forbid")

  zone_id: str = Field(..., min_length=1, max_length=128)
  barn_id: str = Field(..., min_length=1, max_length=128)
  device_id: str = Field(..., min_length=1, max_length=128)
  camera_id: str = Field(..., min_length=1, max_length=128)
  polygon: list[PolygonPoint] = Field(..., min_length=3)
  enabled: bool = True
  label: Optional[str] = Field(None, max_length=200)


class DetectionZoneCreate(DetectionZoneBase):
  pass


class DetectionZoneUpdate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  barn_id: Optional[str] = Field(None, min_length=1, max_length=128)
  device_id: Optional[str] = Field(None, min_length=1, max_length=128)
  camera_id: Optional[str] = Field(None, min_length=1, max_length=128)
  polygon: Optional[list[PolygonPoint]] = Field(None, min_length=3)
  enabled: Optional[bool] = None
  label: Optional[str] = Field(None, max_length=200)


class DetectionZoneResponse(DetectionZoneBase):
  id: Optional[str] = Field(None, alias="_id")
  account_id: str
  created_at: datetime
  updated_at: datetime

  model_config = ConfigDict(populate_by_name=True, extra="allow")


class DeviceAnalyticsExtras(BaseModel):
  device_offline_periods: list[dict[str, Any]]
  queue_backlog_indicators: list[dict[str, Any]]

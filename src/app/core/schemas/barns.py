"""Barn, zone, and device-related Pydantic schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CameraBase(BaseModel):
  camera_id: str
  name: str
  status: str = "active"
  last_seen: Optional[datetime] = None


class CameraCreate(CameraBase):
  pass


class CameraResponse(CameraBase):
  pass


class ZoneBase(BaseModel):
  zone_id: int
  name: str


class ZoneWithCameras(ZoneBase):
  cameras: List[CameraResponse] = []


class ZoneCreate(ZoneBase):
  cameras: List[CameraCreate] = []


class ZoneResponse(ZoneWithCameras):
  pass


class BarnBase(BaseModel):
  barn_id: int
  name: str


class BarnWithZones(BarnBase):
  zones: List[ZoneWithCameras] = []


class BarnCreate(BarnBase):
  zones: List[ZoneCreate] = []


class BarnResponse(BarnWithZones):
  pass


class BarnListResponse(BaseModel):
  barns: List[BarnResponse]


class DetectionItem(BaseModel):
  bbox: List[float]
  confidence: float
  type: str


class DetectionEvent(BaseModel):
  id: int
  timestamp: datetime
  zone_id: int
  device_id: str
  detections: List[DetectionItem]


class DetectionsByDateResponse(BaseModel):
  barn_id: Optional[int] = None
  start_date: str
  end_date: str
  detections: List[DetectionEvent]


class DailySummary(BaseModel):
  date: str
  detections: int


class ReportByDateResponse(BaseModel):
  barn_id: Optional[int] = None
  start_date: str
  end_date: str
  total_detections: int
  high_risk_zones: List[str]
  trend: str
  daily_summary: List[DailySummary]


class AnalyticsByDateResponse(BaseModel):
  start_date: str
  end_date: str
  total_detections: int
  average_confidence: float
  detections_per_barn: dict[str, int]
  trend: str

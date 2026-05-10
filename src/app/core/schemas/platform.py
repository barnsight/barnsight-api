"""Schemas for platform management resources."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class FarmCreate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  name: str = Field(..., min_length=1, max_length=200)
  farm_id: Optional[str] = Field(None, min_length=1, max_length=128)
  account_id: Optional[str] = Field(None, min_length=1, max_length=128)
  location: Optional[str] = Field(None, max_length=200)
  timezone: str = "UTC"


class FarmUpdate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  name: Optional[str] = Field(None, min_length=1, max_length=200)
  location: Optional[str] = Field(None, max_length=200)
  timezone: Optional[str] = None
  status: Optional[Literal["active", "disabled"]] = None


class BarnWrite(BaseModel):
  model_config = ConfigDict(extra="forbid")

  barn_id: str = Field(..., min_length=1, max_length=128)
  name: str = Field(..., min_length=1, max_length=200)
  farm_id: Optional[str] = None
  location: Optional[str] = None
  status: Literal["active", "disabled", "needs_setup"] = "active"


class BarnUpdate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  name: Optional[str] = Field(None, min_length=1, max_length=200)
  farm_id: Optional[str] = None
  location: Optional[str] = None
  status: Optional[Literal["active", "disabled", "needs_setup"]] = None


class GenericPatch(BaseModel):
  model_config = ConfigDict(extra="allow")


class UserCreate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  username: str = Field(..., min_length=1, max_length=80)
  email: str
  password: str = Field(..., min_length=8)
  first_name: str = ""
  middle_name: str = ""
  last_name: str = ""
  role: Literal["super_admin", "admins", "farmers", "staff"] = "staff"
  account_id: Optional[str] = None
  farm_id: Optional[str] = None
  scopes: list[str] = Field(default_factory=list)
  permissions: list[str] = Field(default_factory=list)
  assigned_barn_ids: list[str] = Field(default_factory=list)
  account_date: datetime = Field(default_factory=datetime.utcnow)


class UserStatusUpdate(BaseModel):
  status: Literal["active", "disabled", "pending"]


class UserRoleUpdate(BaseModel):
  role: Literal["super_admin", "admins", "farmers", "staff"]


class StaffBarnAssignment(BaseModel):
  barn_ids: list[str]


class EventStatusUpdate(BaseModel):
  status: Literal["new", "reviewed", "resolved", "false_positive", "ignored"]


class EventReviewUpdate(BaseModel):
  status: Literal["reviewed", "resolved", "false_positive", "ignored"] = "reviewed"
  note: Optional[str] = Field(None, max_length=2000)


class EventNoteCreate(BaseModel):
  note: str = Field(..., min_length=1, max_length=2000)


class ReportGenerateRequest(BaseModel):
  start_date: datetime
  end_date: datetime
  barn_id: Optional[str] = None
  camera_id: Optional[str] = None
  status: Optional[str] = None
  format: Literal["json", "csv", "pdf"] = "json"


class ReportResponse(BaseModel):
  id: Optional[str] = Field(None, alias="_id")
  account_id: str
  farm_id: Optional[str] = None
  name: str
  filters: dict[str, Any]
  status: str
  created_at: datetime

  model_config = ConfigDict(populate_by_name=True, extra="allow")

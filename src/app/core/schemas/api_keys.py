from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
  name: str = Field(..., min_length=1, max_length=120)
  account_id: Optional[str] = None
  farm_id: Optional[str] = None
  barn_id: Optional[str] = None
  device_id: Optional[str] = None
  scopes: list[str] = Field(
    default_factory=lambda: [
      "edge:heartbeat",
      "edge:event:create",
      "edge:snapshot:upload",
      "edge:camera:sync",
      "edge:device:config:read",
    ]
  )
  expires_in_days: Optional[int] = Field(None, description="Optional expiration in days")


class ApiKeyResponse(BaseModel):
  id: str = Field(..., alias="_id")
  name: str
  prefix: str
  key: Optional[str] = Field(None, description="The actual API key, only shown once")
  account_id: str
  farm_id: str
  barn_id: Optional[str] = None
  device_id: Optional[str] = None
  scopes: list[str]
  status: Literal["active", "revoked", "expired"]
  created_by_user_id: Optional[str] = None
  created_at: datetime
  expires_at: Optional[datetime] = None
  last_used_at: Optional[datetime] = None
  last_used_ip: Optional[str] = None
  revoked_at: Optional[datetime] = None

  model_config = ConfigDict(populate_by_name=True, extra="allow")


class ApiKeyRotateResponse(ApiKeyResponse):
  key: str


class ApiKeyScopesUpdate(BaseModel):
  scopes: list[str] = Field(..., min_length=1)


class ApiKeyInDB(BaseModel):
  key_hash: str
  prefix: str
  account_id: str
  farm_id: str
  barn_id: Optional[str] = None
  device_id: Optional[str] = None
  name: str
  scopes: list[str]
  status: Literal["active", "revoked", "expired"]
  created_by_user_id: Optional[str] = None
  created_at: datetime
  expires_at: Optional[datetime] = None
  last_used_at: Optional[datetime] = None
  last_used_ip: Optional[str] = None
  revoked_at: Optional[datetime] = None

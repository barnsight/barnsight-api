"""Admin user schema for initial account creation."""

from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field

from .user import UserName
from .utils import PASSWORDstr


class AdminCreate(UserName):
  """Schema for creating an admin account."""

  username: str
  email: str
  password: PASSWORDstr
  role: str = "admins"
  scopes: List[str] = ["admin"]
  account_date: Optional[datetime] = Field(default_factory=datetime.utcnow)
  account_date: Optional[datetime] = Field(default_factory=datetime.utcnow)

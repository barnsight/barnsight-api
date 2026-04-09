"""User-related Pydantic schemas.

Defines data models for user creation, response, and updates.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from .utils import PASSWORDstr


class UserName(BaseModel):
  """User's full name components."""

  first_name: str
  middle_name: str
  last_name: str


class UserBase(UserName):
  """Base user fields required for all user representations."""

  username: str
  email: EmailStr
  role: str
  account_date: datetime


class UserPrivate(UserBase):
  """User representation that includes password and scopes (never returned to client)."""

  password: Optional[PASSWORDstr] = None
  scopes: List[str]


class UserUpdate(BaseModel):
  """Partial user update — all fields are optional."""

  first_name: Optional[str] = None
  middle_name: Optional[str] = None
  last_name: Optional[str] = None
  role: Optional[str] = None
  scopes: Optional[List[str]] = None

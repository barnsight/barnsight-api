"""Schemas for farmer and staff account registration."""

from typing import List

from .user import UserName
from .utils import PASSWORDstr


class FarmerCreate(UserName):
  """Schema for creating a farmer account."""

  username: str
  email: str
  password: PASSWORDstr
  role: str = "farmers"
  scopes: List[str] = ["farmer"]


class StaffCreate(UserName):
  """Schema for creating a staff account."""

  username: str
  email: str
  password: PASSWORDstr
  role: str = "staff"
  scopes: List[str] = ["staff"]

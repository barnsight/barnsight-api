"""Admin user schema for initial account creation."""

from typing import List
from .user import UserBase


class AdminCreate(UserBase):
  """Schema for creating an admin account."""
  role: str = "admins"
  scopes: List[str] = ["admin"]

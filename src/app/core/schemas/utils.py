"""Shared utility schemas used across multiple endpoints."""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, EmailStr, Field

PASSWORDstr = Annotated[str, Field(..., min_length=8, max_length=128)]
PyObjectId = Annotated[str, BeforeValidator(str)]


class HealthCheck(BaseModel):
  """Simple health check response."""

  status: Literal["ok"] = "ok"


class UpdatePassword(BaseModel):
  """Request body for changing a user's password."""

  current_password: PASSWORDstr
  new_password: PASSWORDstr


class UpdateEmail(BaseModel):
  """Request body for updating a user's email."""

  email: EmailStr
  password: PASSWORDstr


class RecoverPassword(BaseModel):
  """Request body for recovering a user's password."""

  email: EmailStr
  new_password: PASSWORDstr

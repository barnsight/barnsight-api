"""Role and permission helpers for BarnSight API routes."""

from enum import StrEnum
from typing import Iterable

from fastapi import HTTPException, status


class Role(StrEnum):
  SUPER_ADMIN = "super_admin"
  ADMIN = "admins"
  FARMER = "farmers"
  STAFF = "staff"


ROLE_PERMISSIONS: dict[str, set[str]] = {
  Role.SUPER_ADMIN: {"*"},
  Role.ADMIN: {
    "accounts:read",
    "farms:manage",
    "users:manage",
    "barns:manage",
    "devices:manage",
    "cameras:manage",
    "zones:manage",
    "events:manage",
    "reports:manage",
    "api_keys:manage",
    "analytics:read",
  },
  Role.FARMER: {
    "farms:read",
    "barns:manage",
    "devices:read",
    "cameras:read",
    "zones:read",
    "events:review",
    "reports:read",
    "analytics:read",
  },
  Role.STAFF: {
    "barns:read",
    "events:review",
    "reports:read",
    "analytics:read",
  },
}


def account_id_from_user(user: dict) -> str | None:
  """Return the account scope for a user document or JWT payload."""
  return user.get("account_id") or user.get("sub") or user.get("username")


def farm_id_from_user(user: dict) -> str | None:
  """Return the farm scope for a user, falling back to account scope."""
  return user.get("farm_id") or account_id_from_user(user)


def is_super_admin(user: dict) -> bool:
  return user.get("role") == Role.SUPER_ADMIN or "super_admin" in user.get("scopes", [])


def permissions_for_user(user: dict) -> set[str]:
  permissions = set(user.get("permissions", []))
  scopes = set(user.get("scopes", []))
  permissions.update(scopes)
  role = user.get("role")
  permissions.update(ROLE_PERMISSIONS.get(role, set()))
  return permissions


def require_permission(user: dict, required: str | Iterable[str]) -> None:
  """Raise 403 unless the user has one of the required permissions."""
  required_set = {required} if isinstance(required, str) else set(required)
  permissions = permissions_for_user(user)
  if "*" in permissions or permissions.intersection(required_set):
    return
  raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")


def scoped_query(user: dict, extra: dict | None = None) -> dict:
  """Build an ownership-scoped Mongo query."""
  query = dict(extra or {})
  if not is_super_admin(user):
    query["account_id"] = account_id_from_user(user)
  return query

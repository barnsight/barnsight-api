"""Audit logging helpers."""

from datetime import datetime, timezone
from typing import Any


async def write_audit_log(
  db,
  *,
  action: str,
  actor_id: str | None = None,
  account_id: str | None = None,
  farm_id: str | None = None,
  resource_type: str | None = None,
  resource_id: str | None = None,
  metadata: dict[str, Any] | None = None,
) -> None:
  await db["audit_logs"].insert_one(
    {
      "action": action,
      "actor_id": actor_id,
      "account_id": account_id,
      "farm_id": farm_id,
      "resource_type": resource_type,
      "resource_id": resource_id,
      "metadata": metadata or {},
      "created_at": datetime.now(timezone.utc),
    }
  )

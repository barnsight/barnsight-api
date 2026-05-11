import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bson import ObjectId
from core.schemas.api_keys import ApiKeyCreate
from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from .base_crud import BaseCRUD


class ApiKeyCRUD(BaseCRUD):
  def __init__(self, db: AsyncDatabase):
    super().__init__(db)
    self.collection_name = "api_keys"
    self.default_edge_scopes = [
      "edge:heartbeat",
      "edge:event:create",
      "edge:snapshot:upload",
      "edge:camera:sync",
      "edge:device:config:read",
    ]

  def _generate_key(self) -> str:
    """Generates a secure random API key."""
    return f"bs_live_{secrets.token_urlsafe(32)}"

  def _hash_key(self, key: str) -> str:
    """Hashes an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()

  def _prefix(self, raw_key: str) -> str:
    return raw_key[:16]

  def _normalize_raw_key(self, raw_key: str) -> str:
    normalized = raw_key.strip()
    if normalized.lower().startswith("bearer "):
      normalized = normalized[7:].strip()
    return normalized

  def _serialize(self, doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc

  def _response_doc(self, doc: dict, owner_id: str | None = None) -> dict:
    """Return a safe API response shape for current and legacy key documents."""
    key_id = str(doc["_id"])
    account_id = doc.get("account_id") or doc.get("owner_id") or owner_id
    farm_id = doc.get("farm_id") or account_id
    created_at = doc.get("created_at")
    if created_at is None and hasattr(doc.get("_id"), "generation_time"):
      created_at = doc["_id"].generation_time
    if created_at is None:
      created_at = datetime.now(timezone.utc)
    status = doc.get("status")
    if status not in {"active", "revoked", "expired"}:
      status = "active"

    return {
      "_id": key_id,
      "name": doc.get("name") or "Legacy API Key",
      "prefix": doc.get("prefix") or doc.get("key_prefix") or f"legacy_{key_id[-8:]}",
      "account_id": account_id,
      "farm_id": farm_id,
      "barn_id": doc.get("barn_id"),
      "device_id": doc.get("device_id"),
      "scopes": self._normalized_scopes(doc),
      "status": status,
      "created_by_user_id": doc.get("created_by_user_id"),
      "created_at": created_at,
      "expires_at": doc.get("expires_at"),
      "last_used_at": doc.get("last_used_at") or doc.get("last_used"),
      "last_used_ip": doc.get("last_used_ip"),
      "revoked_at": doc.get("revoked_at"),
    }

  def _normalized_scopes(self, doc: dict) -> list[str]:
    scopes = doc.get("scopes")
    if scopes:
      return scopes
    return list(self.default_edge_scopes)

  def _object_id(self, key_id: str) -> ObjectId:
    try:
      return ObjectId(key_id)
    except Exception as exc:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
      ) from exc

  async def _audit(self, action: str, payload: dict) -> None:
    await self.db["audit_logs"].insert_one(
      {"action": action, "created_at": datetime.now(timezone.utc), **payload}
    )

  async def create_key(
    self, owner_id: str, key_data: ApiKeyCreate, created_by: str | None = None
  ) -> dict:
    """Creates and stores a new API key."""
    raw_key = self._generate_key()
    now = datetime.now(timezone.utc)
    account_id = key_data.account_id or owner_id
    farm_id = key_data.farm_id or account_id

    doc = {
      "account_id": account_id,
      "farm_id": farm_id,
      "barn_id": key_data.barn_id,
      "device_id": key_data.device_id,
      "owner_id": owner_id,
      "name": key_data.name,
      "prefix": self._prefix(raw_key),
      "key_hash": self._hash_key(raw_key),
      "scopes": key_data.scopes,
      "status": "active",
      "created_by_user_id": created_by or owner_id,
      "created_at": now,
      "expires_at": (
        now + timedelta(days=key_data.expires_in_days) if key_data.expires_in_days else None
      ),
      "last_used_at": None,
      "last_used_ip": None,
      "revoked_at": None,
    }

    result = await self.db[self.collection_name].insert_one(doc)
    response_doc = {**doc, "_id": result.inserted_id}
    await self._audit(
      "api_key.created",
      {"api_key_id": str(result.inserted_id), "account_id": account_id, "prefix": doc["prefix"]},
    )
    response_doc = self._response_doc(response_doc, owner_id=owner_id)
    response_doc["key"] = raw_key  # Include raw key only for the response
    return response_doc

  async def get_keys_for_owner(self, owner_id: str) -> List[dict]:
    """Retrieves all keys belonging to a specific owner."""
    cursor = self.db[self.collection_name].find(
      {"$or": [{"owner_id": owner_id}, {"account_id": owner_id}, {"farm_id": owner_id}]}
    )
    keys = await cursor.to_list(length=100)
    return [self._response_doc(k, owner_id=owner_id) for k in keys]

  async def validate_key(
    self, raw_key: str, required_scope: str | None = None, ip: str | None = None
  ) -> Optional[dict]:
    """Validates a raw API key and returns the key document if valid."""
    raw_key = self._normalize_raw_key(raw_key)
    if not raw_key:
      await self._audit(
        "api_key.authentication_failed", {"prefix": "", "reason": "empty", "ip": ip}
      )
      return None

    key_hash = self._hash_key(raw_key)
    prefix = self._prefix(raw_key)
    candidates_by_id: dict[object, dict] = {}

    prefix_cursor = self.db[self.collection_name].find(
      {"$or": [{"prefix": prefix}, {"key_prefix": prefix}]}
    )
    for key_doc in await prefix_cursor.to_list(length=25):
      candidates_by_id[key_doc["_id"]] = key_doc

    exact_hash_match = await self.db[self.collection_name].find_one(
      {"$or": [{"key_hash": key_hash}, {"hashed_key": key_hash}]}
    )
    if exact_hash_match:
      candidates_by_id[exact_hash_match["_id"]] = exact_hash_match

    candidates = list(candidates_by_id.values())
    now = datetime.now(timezone.utc)

    for key_doc in candidates:
      stored_hash = key_doc.get("key_hash") or key_doc.get("hashed_key")
      if not stored_hash or not hmac.compare_digest(stored_hash, key_hash):
        continue
      expires_at = key_doc.get("expires_at")
      if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
      expired = bool(expires_at and expires_at <= now)
      active = key_doc.get("status", "active") == "active" and not expired
      scopes = self._normalized_scopes(key_doc)
      has_scope = required_scope is None or required_scope in scopes
      if not active or not has_scope:
        if expired:
          await self.db[self.collection_name].update_one(
            {"_id": key_doc["_id"]}, {"$set": {"status": "expired"}}
          )
        await self._audit(
          "api_key.authentication_failed",
          {"prefix": prefix, "reason": "inactive_or_scope", "ip": ip},
        )
        return None
      await self.db[self.collection_name].update_one(
        {"_id": key_doc["_id"]},
        {"$set": {"last_used_at": now, "last_used_ip": ip, "scopes": scopes}},
      )
      key_doc["scopes"] = scopes
      key_doc["last_used_at"] = now
      key_doc["last_used_ip"] = ip
      return self._serialize(key_doc)
    await self._audit(
      "api_key.authentication_failed", {"prefix": prefix, "reason": "invalid", "ip": ip}
    )
    return None

  async def delete_key(self, owner_id: str, key_id: str) -> bool:
    """Revokes a specific API key without deleting its audit history."""
    now = datetime.now(timezone.utc)
    result = await self.db[self.collection_name].update_one(
      {
        "_id": self._object_id(key_id),
        "$or": [{"owner_id": owner_id}, {"account_id": owner_id}, {"farm_id": owner_id}],
      },
      {"$set": {"status": "revoked", "revoked_at": now}},
    )
    if result.modified_count:
      await self._audit("api_key.revoked", {"api_key_id": key_id, "account_id": owner_id})
    return result.modified_count > 0

  async def rotate_key(self, owner_id: str, key_id: str) -> Optional[dict]:
    existing = await self.db[self.collection_name].find_one(
      {
        "_id": self._object_id(key_id),
        "$or": [{"owner_id": owner_id}, {"account_id": owner_id}, {"farm_id": owner_id}],
      }
    )
    if not existing:
      return None
    raw_key = self._generate_key()
    update = {
      "prefix": self._prefix(raw_key),
      "key_hash": self._hash_key(raw_key),
      "status": "active",
      "last_used_at": None,
      "last_used_ip": None,
      "revoked_at": None,
    }
    await self.db[self.collection_name].update_one({"_id": existing["_id"]}, {"$set": update})
    existing.update(update)
    await self._audit(
      "api_key.rotated",
      {"api_key_id": key_id, "account_id": existing.get("account_id"), "prefix": update["prefix"]},
    )
    existing = self._response_doc(existing, owner_id=owner_id)
    existing["key"] = raw_key
    return existing

  async def update_scopes(self, owner_id: str, key_id: str, scopes: list[str]) -> Optional[dict]:
    await self.db[self.collection_name].update_one(
      {
        "_id": self._object_id(key_id),
        "$or": [{"owner_id": owner_id}, {"account_id": owner_id}, {"farm_id": owner_id}],
      },
      {"$set": {"scopes": scopes}},
    )
    doc = await self.db[self.collection_name].find_one({"_id": self._object_id(key_id)})
    if not doc:
      return None
    await self._audit(
      "api_key.scopes_updated",
      {"api_key_id": key_id, "account_id": doc.get("account_id"), "scopes": scopes},
    )
    return self._response_doc(doc, owner_id=owner_id)

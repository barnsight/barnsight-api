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

  def _generate_key(self) -> str:
    """Generates a secure random API key."""
    return f"bs_live_{secrets.token_urlsafe(32)}"

  def _hash_key(self, key: str) -> str:
    """Hashes an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()

  def _prefix(self, raw_key: str) -> str:
    return raw_key[:16]

  def _serialize(self, doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc

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
    response_doc = self._serialize(response_doc)
    response_doc["key"] = raw_key  # Include raw key only for the response
    return response_doc

  async def get_keys_for_owner(self, owner_id: str) -> List[dict]:
    """Retrieves all keys belonging to a specific owner."""
    cursor = self.db[self.collection_name].find(
      {"$or": [{"owner_id": owner_id}, {"account_id": owner_id}, {"farm_id": owner_id}]}
    )
    keys = await cursor.to_list(length=100)
    for k in keys:
      self._serialize(k)
    return keys

  async def validate_key(
    self, raw_key: str, required_scope: str | None = None, ip: str | None = None
  ) -> Optional[dict]:
    """Validates a raw API key and returns the key document if valid."""
    key_hash = self._hash_key(raw_key)
    prefix = self._prefix(raw_key)
    cursor = self.db[self.collection_name].find({"prefix": prefix})
    candidates = await cursor.to_list(length=25)
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
      has_scope = required_scope is None or required_scope in key_doc.get("scopes", [])
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
        {"_id": key_doc["_id"]}, {"$set": {"last_used_at": now, "last_used_ip": ip}}
      )
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
    existing = self._serialize(existing)
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
    return self._serialize(doc)

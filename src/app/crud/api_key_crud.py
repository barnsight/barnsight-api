import secrets
import hashlib
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from .base_crud import BaseCRUD
from core.schemas.api_keys import ApiKeyCreate

class ApiKeyCRUD(BaseCRUD):
    def __init__(self, db: AsyncDatabase):
        super().__init__(db)
        self.collection_name = "api_keys"

    def _generate_key(self) -> str:
        """Generates a secure random API key."""
        return f"bs_{secrets.token_urlsafe(32)}"

    def _hash_key(self, key: str) -> str:
        """Hashes an API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()

    async def create_key(self, owner_id: str, key_data: ApiKeyCreate) -> dict:
        """Creates and stores a new API key."""
        raw_key = self._generate_key()
        hashed_key = self._hash_key(raw_key)
        
        doc = {
            "owner_id": owner_id,
            "name": key_data.name,
            "hashed_key": hashed_key,
            "created_at": datetime.utcnow(),
            "last_used": None
        }
        
        result = await self.db[self.collection_name].insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        doc["key"] = raw_key  # Include raw key only for the response
        return doc

    async def get_keys_for_owner(self, owner_id: str) -> List[dict]:
        """Retrieves all keys belonging to a specific owner."""
        cursor = self.db[self.collection_name].find({"owner_id": owner_id})
        keys = await cursor.to_list(length=100)
        for k in keys:
            k["_id"] = str(k["_id"])
        return keys

    async def validate_key(self, raw_key: str) -> Optional[dict]:
        """Validates a raw API key and returns the key document if valid."""
        hashed_key = self._hash_key(raw_key)
        key_doc = await self.db[self.collection_name].find_one({"hashed_key": hashed_key})
        
        if key_doc:
            # Update last_used timestamp
            await self.db[self.collection_name].update_one(
                {"_id": key_doc["_id"]},
                {"$set": {"last_used": datetime.utcnow()}}
            )
            key_doc["_id"] = str(key_doc["_id"])
            return key_doc
        return None

    async def delete_key(self, owner_id: str, key_id: str) -> bool:
        """Deletes a specific API key."""
        result = await self.db[self.collection_name].delete_one({
            "_id": ObjectId(key_id),
            "owner_id": owner_id
        })
        return result.deleted_count > 0

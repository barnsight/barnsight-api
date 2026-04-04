"""API key authentication dependency for edge devices.

Validates X-API-Key header against stored keys in MongoDB.
"""

from typing import Optional

from fastapi import Request, Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from core.database import MongoClient
from crud.api_key_crud import ApiKeyCRUD

# Header name for edge device API keys
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def validate_api_key(
  request: Request,
  api_key: Optional[str] = Depends(api_key_header),
  mongo: MongoClient = Depends(lambda: MongoClient),
):
  """Validate an API key from the X-API-Key header.

  Returns the key document if valid, None otherwise.
  The owner_id is stored in request.state for downstream use.
  """
  if not api_key:
    return None

  if not MongoClient._client:
    MongoClient.connect()

  db = mongo.get_database("users")
  api_key_crud = ApiKeyCRUD(db)

  key_doc = await api_key_crud.validate_key(api_key)
  if not key_doc:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid API Key",
    )

  request.state.api_key_owner = key_doc.get("owner_id")
  return key_doc

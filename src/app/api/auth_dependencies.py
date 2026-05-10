"""API key authentication dependency for edge devices."""

from typing import Optional

from core.database import MongoClient
from crud.api_key_crud import ApiKeyCRUD
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-BarnSight-Key", auto_error=False)
legacy_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def validate_api_key(
  request: Request,
  api_key: Optional[str] = Depends(api_key_header),
  legacy_api_key: Optional[str] = Depends(legacy_api_key_header),
  mongo: MongoClient = Depends(lambda: MongoClient),
):
  """Validate an API key from the X-BarnSight-Key header.

  Returns the key document if valid, None otherwise.
  X-API-Key is accepted only for backward compatibility with older edge clients.
  """
  raw_key = api_key or legacy_api_key
  if not raw_key:
    return None

  if not MongoClient._client:
    await MongoClient.connect()

  db = mongo.get_database("users")
  api_key_crud = ApiKeyCRUD(db)

  key_doc = await api_key_crud.validate_key(
    raw_key, ip=request.client.host if request.client else None
  )
  if not key_doc:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid API Key",
    )

  request.state.api_key_owner = key_doc.get("account_id") or key_doc.get("owner_id")
  request.state.edge_context = key_doc
  return key_doc


def require_edge_scope(scope: str):
  async def dependency(
    request: Request,
    api_key: Optional[str] = Depends(api_key_header),
    legacy_api_key: Optional[str] = Depends(legacy_api_key_header),
    mongo: MongoClient = Depends(lambda: MongoClient),
  ) -> dict:
    raw_key = api_key or legacy_api_key
    if not raw_key:
      raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-BarnSight-Key"
      )
    if not MongoClient._client:
      await MongoClient.connect()
    db = mongo.get_database("users")
    key_doc = await ApiKeyCRUD(db).validate_key(
      raw_key, required_scope=scope, ip=request.client.host if request.client else None
    )
    if not key_doc:
      raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid, inactive, expired, or unauthorized API key",
      )
    request.state.edge_context = key_doc
    return key_doc

  return dependency

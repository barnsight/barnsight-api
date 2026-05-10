from typing import Annotated, List

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.api_keys import (
  ApiKeyCreate,
  ApiKeyResponse,
  ApiKeyRotateResponse,
  ApiKeyScopesUpdate,
)
from crud.api_key_crud import ApiKeyCRUD
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(tags=["API Keys"])


@router.post(
  "",
  status_code=status.HTTP_201_CREATED,
  response_model=ApiKeyResponse,
  dependencies=[Depends(limit_dependency)],
)
async def create_api_key(
  key_data: ApiKeyCreate,
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """
  Generate a new API key for the current account.
  """
  db = mongo.get_database("users")
  api_key_crud = ApiKeyCRUD(db)

  # We use username or a unique ID from the user profile as owner_id
  owner_id = current_user.get("sub") or current_user.get("username")
  new_key = await api_key_crud.create_key(
    owner_id, key_data, created_by=current_user.get("username")
  )
  return new_key


@router.get(
  "",
  status_code=status.HTTP_200_OK,
  response_model=List[ApiKeyResponse],
  response_model_exclude={"key"},
  dependencies=[Depends(limit_dependency)],
)
async def list_api_keys(
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """
  List all API keys belonging to the current account.
  """
  db = mongo.get_database("users")
  api_key_crud = ApiKeyCRUD(db)

  owner_id = current_user.get("sub") or current_user.get("username")
  keys = await api_key_crud.get_keys_for_owner(owner_id)
  return keys


@router.delete(
  "/{key_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def delete_api_key(
  key_id: str,
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """
  Revoke a specific API key.
  """
  db = mongo.get_database("users")
  api_key_crud = ApiKeyCRUD(db)

  owner_id = current_user.get("sub") or current_user.get("username")
  deleted = await api_key_crud.delete_key(owner_id, key_id)
  if not deleted:
    raise HTTPException(status_code=404, detail="API key not found")
  return


@router.post(
  "/{key_id}/rotate",
  status_code=status.HTTP_200_OK,
  response_model=ApiKeyRotateResponse,
  dependencies=[Depends(limit_dependency)],
)
async def rotate_api_key(
  key_id: str,
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("users")
  owner_id = current_user.get("sub") or current_user.get("username")
  rotated = await ApiKeyCRUD(db).rotate_key(owner_id, key_id)
  if not rotated:
    raise HTTPException(status_code=404, detail="API key not found")
  return rotated


@router.patch(
  "/{key_id}/scopes",
  status_code=status.HTTP_200_OK,
  response_model=ApiKeyResponse,
  dependencies=[Depends(limit_dependency)],
)
async def update_api_key_scopes(
  key_id: str,
  scope_data: ApiKeyScopesUpdate,
  current_user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("users")
  owner_id = current_user.get("sub") or current_user.get("username")
  updated = await ApiKeyCRUD(db).update_scopes(owner_id, key_id, scope_data.scopes)
  if not updated:
    raise HTTPException(status_code=404, detail="API key not found")
  return updated

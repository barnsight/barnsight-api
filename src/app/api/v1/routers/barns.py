"""Barn management routes.

Handles listing and retrieving barns with their zones and cameras.
"""

from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.barns import BarnListResponse, BarnResponse
from crud.barn_crud import BarnCRUD
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(tags=["Barns"])


@router.get(
  "",
  status_code=status.HTTP_200_OK,
  response_model=BarnListResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_barns(
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return all barns accessible to the user."""
  db = mongo.get_database("barnsight")
  barn_crud = BarnCRUD(db)

  username = user.get("username")
  role = user.get("role", "")
  account_id = user.get("sub")

  barn_ids = await barn_crud.get_barn_ids_for_user(username, role)
  all_barns = await barn_crud.get_all_barns(account_id=account_id)

  if barn_ids is not None:
    all_barns = [b for b in all_barns if b["barn_id"] in barn_ids]

  return {"barns": all_barns}


@router.get(
  "/{barn_id}",
  status_code=status.HTTP_200_OK,
  response_model=BarnResponse,
  dependencies=[Depends(limit_dependency)],
)
async def get_barn(
  barn_id: int,
  user: Annotated[dict, Depends(get_current_user)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Return a single barn by ID with its zones and cameras."""
  db = mongo.get_database("barnsight")
  barn_crud = BarnCRUD(db)

  username = user.get("username")
  role = user.get("role", "")
  account_id = user.get("sub")

  barn_ids = await barn_crud.get_barn_ids_for_user(username, role)

  if barn_ids is not None and barn_id not in barn_ids:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Access denied to this barn.",
    )

  barn = await barn_crud.get_barn_by_id(barn_id, account_id=account_id)
  if not barn:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail="Barn not found.",
    )

  return barn

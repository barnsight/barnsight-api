"""Farmers management routes."""

from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, limit_dependency
from core.database import MongoClient
from core.schemas.platform import GenericPatch
from core.schemas.registration import FarmerCreate
from crud import UserCRUD
from fastapi import APIRouter, Body, Depends, HTTPException, Response, Security, status

router = APIRouter(tags=["Farmers"])


@router.post(
  "",
  status_code=status.HTTP_201_CREATED,
  dependencies=[Security(get_current_user, scopes=["admin"]), Depends(limit_dependency)],
)
async def register_farmer(
  farmer: Annotated[FarmerCreate, Body()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Register a new farmer account. Admin only."""
  users_db = mongo.get_database("users")
  if await UserCRUD(users_db).find(username=farmer.username):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Username already exists.",
    )

  await UserCRUD(users_db).create(farmer)
  return {"message": "Farmer account created successfully."}


@router.get("", status_code=status.HTTP_200_OK, dependencies=[Depends(limit_dependency)])
async def list_farmers(
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  cursor = users_db["farmers"].find({})
  farmers = await cursor.to_list(length=None)
  for farmer in farmers:
    farmer["_id"] = str(farmer["_id"])
    farmer.pop("password", None)
  return {"farmers": farmers}


@router.get(
  "/{farmer_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(limit_dependency)]
)
async def get_farmer(
  farmer_id: str,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  farmer = await users_db["farmers"].find_one({"username": farmer_id})
  if not farmer:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farmer not found")
  farmer["_id"] = str(farmer["_id"])
  farmer.pop("password", None)
  return farmer


@router.patch(
  "/{farmer_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(limit_dependency)]
)
async def update_farmer(
  farmer_id: str,
  update: GenericPatch,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  data = update.model_dump(exclude_unset=True)
  data.pop("password", None)
  result = await users_db["farmers"].update_one({"username": farmer_id}, {"$set": data})
  if result.modified_count == 0:
    existing = await users_db["farmers"].find_one({"username": farmer_id})
    if not existing:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farmer not found")
  return {"message": "Farmer updated."}


@router.delete(
  "/{farmer_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(limit_dependency)]
)
async def delete_farmer(
  farmer_id: str,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  _: Annotated[dict, Depends(get_current_user)],
):
  users_db = mongo.get_database("users")
  result = await users_db["farmers"].delete_one({"username": farmer_id})
  if result.deleted_count == 0:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farmer not found")
  return Response(status_code=status.HTTP_204_NO_CONTENT)

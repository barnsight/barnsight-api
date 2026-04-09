"""Device management and heartbeat routes."""

from typing import Annotated

from api.auth_dependencies import validate_api_key
from core.database import RedisClient
from fastapi import APIRouter, Depends, status

router = APIRouter(tags=["Devices"])


@router.post(
  "/heartbeat",
  status_code=status.HTTP_204_NO_CONTENT,
)
async def device_heartbeat(
  api_key_data: Annotated[dict, Depends(validate_api_key)],
):
  """Register a heartbeat for an edge device to track its online status."""
  owner_id = api_key_data.get("owner_id")
  device_id = api_key_data.get("device_id") or "default"

  redis = RedisClient()
  key = f"device:{owner_id}:{device_id}:status"

  # Set status to online with a 5-minute TTL
  await redis.setex(key, 300, "online")
  return None

"""System metadata and health routes."""

from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, get_redis_client, limit_dependency
from core.config import settings
from core.database import MongoClient, RedisClient
from core.permissions import require_permission
from fastapi import APIRouter, Depends, status

router = APIRouter(tags=["System"])


@router.get("/version", status_code=status.HTTP_200_OK)
async def system_version():
  return {"name": settings.NAME, "version": settings.VERSION, "api": settings.API_V1_STR}


@router.get("/config", dependencies=[Depends(limit_dependency)])
async def system_config(
  user: Annotated[dict, Depends(get_current_user)],
):
  require_permission(user, "accounts:read")
  return {
    "cors_origins": settings.all_cors_origins,
    "edge_max_snapshot_bytes": settings.EDGE_MAX_SNAPSHOT_BYTES,
    "device_heartbeat_ttl_seconds": settings.DEVICE_HEARTBEAT_TTL_SECONDS,
    "rate_limits": settings.RATE_LIMITS,
  }


@router.get("/health", dependencies=[Depends(limit_dependency)])
async def system_health(
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  mongo_ok = bool(mongo)
  redis_ok = bool(redis)
  return {
    "status": "ok" if mongo_ok and redis_ok else "degraded",
    "database": "ok" if mongo_ok else "unavailable",
    "redis": "ok" if redis_ok else "unavailable",
    "storage": "configured"
    if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY
    else "not_configured",
  }

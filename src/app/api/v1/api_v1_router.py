from fastapi import APIRouter
from .routers import (
  health,
  google_auth,
  auth,
  user,
  users,
  admin,
  events,
  analytics,
  api_keys
)

# Initialize v1 router
api_v1_router = APIRouter()

# Include routers
api_v1_router.include_router(health.router, prefix="/health")
api_v1_router.include_router(google_auth.router, prefix="/auth")
api_v1_router.include_router(auth.router, prefix="/auth")
api_v1_router.include_router(user.router, prefix="/user")
api_v1_router.include_router(users.router, prefix="/users")
api_v1_router.include_router(admin.router, prefix="/admin")
api_v1_router.include_router(events.router, prefix="/events")
api_v1_router.include_router(analytics.router, prefix="/analytics")
api_v1_router.include_router(api_keys.router, prefix="/api-keys")

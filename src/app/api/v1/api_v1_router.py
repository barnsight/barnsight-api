from fastapi import APIRouter

from .routers import (
  admin,
  analytics,
  api_keys,
  auth,
  barns,
  cameras,
  detections,
  devices,
  edge,
  events,
  farmers,
  farms,
  google_auth,
  health,
  reports,
  staff,
  system,
  user,
  users,
  ws,
  zones,
)

# Initialize v1 router
api_v1_router = APIRouter()

# Include routers
api_v1_router.include_router(health.router, prefix="/health")
api_v1_router.include_router(google_auth.router, prefix="/auth")
api_v1_router.include_router(auth.router, prefix="/auth")
api_v1_router.include_router(user.router, prefix="/user")
api_v1_router.include_router(user.router)
api_v1_router.include_router(users.router, prefix="/users")
api_v1_router.include_router(admin.router, prefix="/admin")
api_v1_router.include_router(farms.router, prefix="/farms")
api_v1_router.include_router(farmers.router, prefix="/farmers")
api_v1_router.include_router(staff.router, prefix="/staff")
api_v1_router.include_router(events.router, prefix="/events")
api_v1_router.include_router(ws.router, prefix="/ws")
api_v1_router.include_router(devices.router, prefix="/devices")
api_v1_router.include_router(edge.router, prefix="/edge")
api_v1_router.include_router(cameras.router, prefix="/cameras")
api_v1_router.include_router(zones.router, prefix="/zones")
api_v1_router.include_router(analytics.router, prefix="/analytics")
api_v1_router.include_router(api_keys.router, prefix="/api-keys")
api_v1_router.include_router(barns.router, prefix="/barns")
api_v1_router.include_router(detections.router, prefix="/detections")
api_v1_router.include_router(reports.router, prefix="/reports")
api_v1_router.include_router(system.router, prefix="/system")

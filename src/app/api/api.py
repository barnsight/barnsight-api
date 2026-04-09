from core.config import settings
from fastapi import APIRouter

# Import API routers
from .v1 import api_v1_router

# Initialize main router
api_main_router = APIRouter()

# Include API routers to the main router
api_main_router.include_router(api_v1_router, prefix=settings.API_V1_STR)

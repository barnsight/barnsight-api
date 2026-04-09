"""BarnSight API — FastAPI application factory.

Sets up middleware, routers, database connections, and monitoring.
"""

from contextlib import asynccontextmanager

from api.api import api_main_router
from api.dependencies import limiter
from core.config import settings
from core.database import MongoClient, RedisClient
from core.errors import rate_limit_exceeded_handler
from core.middleware import RateLimitMiddleware
from core.services.cloudinary_service import init_cloudinary
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
  """Manage application startup and shutdown lifecycle."""
  await RedisClient.connect()
  await MongoClient.connect()
  init_cloudinary()
  try:
    yield
  finally:
    await MongoClient.close()
    await RedisClient.close()


def create_app() -> FastAPI:
  """Create and configure the FastAPI application instance."""
  app = FastAPI(
    title=settings.NAME,
    description=settings.DESCRIPTION,
    summary=settings.SUMMARY,
    version=settings.VERSION,
    openapi_url="/openapi.json",
    lifespan=lifespan,
  )

  # Rate limiting middleware
  app.add_middleware(RateLimitMiddleware)

  # Session middleware with configurable HTTPS enforcement
  app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="session",
    same_site="lax",
    https_only=False,  # Set True behind a reverse proxy with TLS
  )

  # Attach rate limiter and error handler
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

  # CORS middleware
  if settings.all_cors_origins:
    app.add_middleware(
      CORSMiddleware,
      allow_origins=settings.all_cors_origins,
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
    )

  # Prometheus metrics
  Instrumentator().instrument(app).expose(app, endpoint="/metrics")

  # Include API routers
  app.include_router(api_main_router)

  return app


app = create_app()


if __name__ == "__main__":
  import uvicorn

  uvicorn.run(
    app="app.main:app",
    host="0.0.0.0",
    port=8000,
    reload=True,
    log_level="info",
  )

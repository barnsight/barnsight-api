"""Application settings loaded from environment variables.

Uses pydantic-settings for type-validated configuration
with automatic .env file loading.
"""

import secrets
from typing import Annotated, Any, Dict, List, Optional, TypeVar

from pydantic import AnyUrl, BaseModel, BeforeValidator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Generic type variable for CRUD operations
ModelType = TypeVar("ModelType", bound=BaseModel)


def parse_cors(v: Any) -> List[str]:
  """Parse CORS origins from comma-separated string or list.

  Filters out comment lines (starting with #) and empty strings.
  """
  if isinstance(v, str) and not v.startswith("["):
    return [
      item.strip() for item in v.split(",") if item.strip() and not item.strip().startswith("#")
    ]
  if isinstance(v, (list, str)):
    return v
  raise ValueError(v)


class Settings(BaseSettings):
  """BarnSight API configuration."""

  model_config = SettingsConfigDict(
    env_file=".env",
    env_ignore_empty=True,
    extra="ignore",
  )

  # App settings
  NAME: str = "BarnSight API"
  DESCRIPTION: str = "Central ingestion and analytics server for BarnSight farm hygiene monitoring"
  SUMMARY: str = "BarnSight API"
  VERSION: str = "0.1.0"

  FRONTEND_HOST: str = "http://localhost:8000"

  BACKEND_CORS_ORIGINS: Annotated[List[AnyUrl] | str, BeforeValidator(parse_cors)] = []

  @computed_field  # type: ignore[prop-decorator]
  @property
  def all_cors_origins(self) -> List[str]:
    """Return all allowed CORS origins including the frontend host."""
    return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [self.FRONTEND_HOST]

  # API version
  API_V1_STR: str = "/api/v1"

  # Direct URI overrides for cloud deployments (e.g., Render)
  MONGO_URI_OVERRIDE: Optional[str] = None
  REDIS_URL: Optional[str] = None

  # MongoDB settings
  MONGO_HOSTNAME: str = "localhost"
  MONGO_PORT: int = 27017
  MONGO_USERNAME: str = "root"
  MONGO_PASSWORD: str = "root"
  MONGO_MAX_POOL_SIZE: int = 100
  MONGO_MIN_POOL_SIZE: int = 10
  MONGO_CONNECT_TIMEOUT_MS: int = 10000
  MONGO_SERVER_SELECTION_TIMEOUT_MS: int = 10000
  MONGO_RETRY_WRITES: bool = True

  @computed_field  # type: ignore[prop-decorator]
  @property
  def MONGO_URI(self) -> str:
    """Build MongoDB URI from settings, supporting both Atlas and local."""
    if self.MONGO_URI_OVERRIDE:
      return self.MONGO_URI_OVERRIDE

    scheme = "mongodb"
    if "." in self.MONGO_HOSTNAME and "mongodb.net" in self.MONGO_HOSTNAME:
      scheme = "mongodb+srv"
      return f"{scheme}://{self.MONGO_USERNAME}:{self.MONGO_PASSWORD}@{self.MONGO_HOSTNAME}/nosql?authSource=admin"

    return f"{scheme}://{self.MONGO_USERNAME}:{self.MONGO_PASSWORD}@{self.MONGO_HOSTNAME}:{self.MONGO_PORT}/nosql?authSource=admin"

  # Redis settings
  REDIS_HOST: str = "localhost"
  REDIS_PORT: int = 6379
  REDIS_USERNAME: str = ""
  REDIS_PASSWORD: str = ""
  REDIS_DB: int = 0

  CACHE_EXPIRE_MINUTES: int = 60

  # Rate limits
  RATE_LIMIT_ANONYMOUS: str = "100/minute"
  RATE_LIMIT_EDGE: str = "1000/minute"
  RATE_LIMIT_USER: str = "300/minute"

  # Google OAuth settings
  GOOGLE_CLIENT_ID: Optional[str] = None
  GOOGLE_CLIENT_SECRET: Optional[str] = None
  GOOGLE_FRONTEND_REDIRECT: Optional[str] = None

  # Cloudinary settings
  CLOUDINARY_CLOUD_NAME: Optional[str] = None
  CLOUDINARY_API_KEY: Optional[str] = None
  CLOUDINARY_API_SECRET: Optional[str] = None

  # Edge device ingestion and status settings
  EDGE_MAX_SNAPSHOT_BYTES: int = 2_000_000
  DEVICE_HEARTBEAT_TTL_SECONDS: int = 300

  # Session secret — must be set in production
  SECRET_KEY: str = secrets.token_urlsafe(32)

  # JWT settings
  JWT_ALGORITHM: str = "RS256"
  JWT_EXPIRE_MINUTES: int = 60

  PRIVATE_KEY_PEM: Optional[str] = None
  PUBLIC_KEY_PEM: Optional[str] = None

  def model_post_init(self, __context: Any) -> None:
    """Generate RSA keys if not provided in environment."""
    if not self.PRIVATE_KEY_PEM or not self.PUBLIC_KEY_PEM:
      from core.logger import logger
      from core.security.keys import generate_rsa_key_pair

      logger.info("Generating new RSA key pair for JWT signing")
      private, public = generate_rsa_key_pair()
      self.PRIVATE_KEY_PEM = self.PRIVATE_KEY_PEM or private
      self.PUBLIC_KEY_PEM = self.PUBLIC_KEY_PEM or public

  @computed_field  # type: ignore[prop-decorator]
  @property
  def RATE_LIMITS(self) -> Dict[str, str]:
    """Return rate limits as a dict keyed by role."""
    return {
      "anonymous": self.RATE_LIMIT_ANONYMOUS,
      "edge": self.RATE_LIMIT_EDGE,
      "user": self.RATE_LIMIT_USER,
    }


settings = Settings()

# Build Redis URI based on auth configuration
if settings.REDIS_URL:
  REDIS_URI = settings.REDIS_URL
elif settings.REDIS_USERNAME or settings.REDIS_PASSWORD:
  REDIS_URI = f"redis://{settings.REDIS_USERNAME}:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
else:
  REDIS_URI = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

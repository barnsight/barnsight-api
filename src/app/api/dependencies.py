"""FastAPI dependency injection layer.

Provides database clients, authentication, rate limiting,
and JWT extraction for all route handlers.
"""

from typing import Annotated, AsyncGenerator, Optional
from datetime import timedelta
import json

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.logger import logger
from core.config import settings, REDIS_URI
from core.security.jwt import OAuthJWTBearer
from core.database import MongoClient, RedisClient
from crud import UserCRUD


def get_identifier(request: Request) -> str:
  """Extract client identifier for rate limiting from request state."""
  return getattr(request.state, "identifier", get_remote_address(request))


# Initialize rate limiter with per-role default limits
limiter = Limiter(
  key_func=get_identifier,
  default_limits=[settings.RATE_LIMIT_ANONYMOUS],
  strategy="moving-window",
  storage_uri=REDIS_URI,
  headers_enabled=False,
  swallow_errors=False,
)

# OAuth2 scheme for JWT-based authentication
oauth2_scheme = OAuth2PasswordBearer(
  tokenUrl=f"{settings.API_V1_STR}/auth/login",
)


async def get_mongo_client() -> AsyncGenerator[MongoClient, None]:
  """Yield the shared MongoDB async client, connecting if needed."""
  if not MongoClient._client:
    await MongoClient.connect()
  yield MongoClient._client


async def get_redis_client() -> AsyncGenerator[RedisClient, None]:
  """Yield the shared Redis async client, connecting if needed."""
  if not RedisClient._client:
    await RedisClient.connect()
  yield RedisClient._client


async def get_current_user(
  token: Annotated[str, Depends(oauth2_scheme)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  security_scopes: SecurityScopes,
) -> dict:
  """Validate JWT and return the authenticated user document.

  Checks token signature, blacklist status, and scope requirements.
  Caches user profile in Redis for performance.
  """
  payload = OAuthJWTBearer.decode(token=token)
  if payload is None:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid token.",
    )

  username, jti = payload.get("sub"), payload.get("jti")

  # Reject revoked tokens
  if jti and await OAuthJWTBearer.is_jti_in_blacklist(redis, jti=jti):
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Token has been revoked.",
    )

  redis_key = f"cache:user:{username}:profile"
  user = None

  # Try Redis cache first
  if user_cache := await redis.get(redis_key):
    try:
      user = json.loads(user_cache)
    except json.JSONDecodeError as e:
      logger.error(
        {"message": "Failed to decode user cache from Redis", "detail": str(e)},
        exc_info=True,
      )

  # Fall back to MongoDB
  if user is None:
    users_db = mongo.get_database(settings.MONGO_DATABASE)
    user = await UserCRUD(users_db).find(username=username, exclude=["_id", "password"])
    if user is None:
      raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Couldn't validate user credentials.",
        headers={"WWW-Authenticate": "Bearer"},
      )
    await redis.setex(
      redis_key,
      int(timedelta(minutes=settings.CACHE_EXPIRE_MINUTES).total_seconds()),
      json.dumps(user, default=str),
    )

  # Enforce scope requirements
  if security_scopes.scopes:
    user_scopes = user.get("scopes", [])
    if not any(scope in security_scopes.scopes for scope in user_scopes):
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions.",
      )

  return user


def get_jwt_payload(request: Request) -> Optional[dict]:
  """Extract and decode JWT payload from the Authorization header.

  Returns None if no valid token is present — does not raise.
  """
  auth_token = request.headers.get("Authorization")
  if not auth_token:
    return None
  try:
    access_token = auth_token.split()[1]
    return OAuthJWTBearer.decode(token=access_token)
  except Exception:
    return None


def _set_name_from_func(func):
  """Copy the original function's __name__ and __module__ to a wrapper."""

  def decorator(f):
    f.__name__ = func.__name__
    f.__module__ = func.__module__
    return f

  return decorator


async def limit_dependency(request: Request) -> None:
  """Apply dynamic rate limiting based on request.state values."""
  limiter: Limiter = request.app.state.limiter

  @_set_name_from_func(request.scope.get("endpoint"))
  async def dummy(request: Request):
    pass

  limit_value = getattr(request.state, "limit_value", settings.RATE_LIMIT_ANONYMOUS)

  def key_func(request: Request) -> str:
    return getattr(request.state, "identifier", request.client.host)

  endpoint_key = f"{dummy.__module__}.{dummy.__name__}"
  limiter._route_limits.pop(endpoint_key, None)

  check_request_limit = limiter.limit(
    limit_value=limit_value,
    key_func=key_func,
  )(dummy)

  await check_request_limit(request)
  return None

"""JWT encoding, decoding, and blacklist management.

Uses RSA asymmetric keys (RS256) for token signing.
Token revocation is handled via a Redis-backed JTI blacklist.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from core.config import settings
from core.database import RedisClient
from core.logger import logger


class OAuthJWTBearer:
  """JSON Web Token operations using RSA asymmetric encryption."""

  @staticmethod
  def encode(payload: dict) -> dict:
    """Encode a payload into a signed JWT.

    Automatically adds jti, exp, and iat claims.
    Returns the encoded JWT string and the jti for blacklist tracking.
    """
    jti = uuid.uuid4().hex
    payload.update(
      {
        "jti": jti,
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        "iat": datetime.now(tz=timezone.utc),
      }
    )
    return {
      "jwt": jwt.encode(
        payload=payload, key=settings.PRIVATE_KEY_PEM, algorithm=settings.JWT_ALGORITHM
      ),
      "jti": jti,
    }

  @staticmethod
  def decode(token: str) -> Optional[dict]:
    """Decode and verify a JWT. Returns None on failure."""
    try:
      return jwt.decode(jwt=token, key=settings.PUBLIC_KEY_PEM, algorithms=[settings.JWT_ALGORITHM])
    except (jwt.DecodeError, jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
      logger.debug({"message": "JWT decode failed", "detail": str(e)})
      return None

  @staticmethod
  async def refresh(payload: dict) -> str:
    """Re-encode a payload with a fresh expiry and new jti."""
    payload["jti"] = uuid.uuid4().hex
    payload["exp"] = datetime.now(tz=timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(
      payload=payload, key=settings.PRIVATE_KEY_PEM, algorithm=settings.JWT_ALGORITHM
    )

  @staticmethod
  async def add_jti_to_blacklist(redis: RedisClient, *, jti: str, exp: int) -> bool:
    """Blacklist a token by its jti in Redis with TTL matching token expiry."""
    now = int(datetime.now(tz=timezone.utc).timestamp())
    ttl = exp - now
    if ttl < 0:
      logger.warning(f"Token jti={jti} already expired, skipping blacklist")
      return False
    await redis.setex(f"session:blacklist:jti:{jti}", ttl, "Revoked")
    return True

  @staticmethod
  async def is_jti_in_blacklist(redis: RedisClient, *, jti: str) -> bool:
    """Check if a token jti has been revoked."""
    result = await redis.exists(f"session:blacklist:jti:{jti}")
    return bool(result)

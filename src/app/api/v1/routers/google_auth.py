"""Google OAuth2 login flow.

Handles redirect to Google, token exchange, JWT issuance,
and secure cookie setting for the frontend.
"""

from typing import Annotated
from datetime import timedelta

from fastapi.responses import RedirectResponse
from fastapi import HTTPException, APIRouter, Request, status, Depends
import json

from authlib.integrations.base_client.errors import MismatchingStateError, OAuthError

from core.logger import logger
from core.config import settings
from core.security.jwt import OAuthJWTBearer
from core.services.oauth import google_oauth
from core.database import MongoClient, RedisClient
from api.dependencies import get_mongo_client, get_redis_client, limit_dependency
from crud import UserCRUD
from redis.asyncio import Redis

router = APIRouter(tags=["Authentication"])


@router.get(
  "/google",
  operation_id="AuthGoogle",
  dependencies=[Depends(limit_dependency)],
)
async def login_google(request: Request):
  """Redirect to Google's OAuth2 consent screen."""
  redirect_uri = str(request.url_for("auth_google"))
  return await google_oauth.google.authorize_redirect(request, redirect_uri=redirect_uri)


@router.get(
  "/google/callback",
  status_code=status.HTTP_307_TEMPORARY_REDIRECT,
  operation_id="AuthGoogleCallback",
  dependencies=[Depends(limit_dependency)],
)
async def auth_google(
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[Redis, Depends(get_redis_client)],
  request: Request,
):
  """Handle Google OAuth2 callback, issue JWT, and set secure cookies."""
  try:
    token: dict = await google_oauth.google.authorize_access_token(request)
  except MismatchingStateError as e:
    logger.warning(
      {"message": "OAuth state mismatch (CSRF triggered)", "detail": str(e)},
      exc_info=False,
    )
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="Authentication failed due to security check (state mismatch). Please try logging in again.",
    )
  except OAuthError as e:
    logger.warning(
      {"message": "OAuth error during token exchange", "detail": str(e)},
      exc_info=True,
    )
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="Internal authentication error. Please try again later.",
    )

  user = token.get("userinfo")
  if not user:
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="The server is temporarily unable to process the request.",
    )

  user_email = user["email"]
  users_db = mongo.get_database("users")
  user_doc = await UserCRUD(users_db).find(username=user_email)
  if not user_doc:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Couldn't validate credentials",
      headers={"WWW-Authenticate": "Bearer"},
    )

  edbo_id, role, scopes = user_doc.get("edbo_id"), user_doc.get("role"), user_doc.get("scopes")

  jwt_data = OAuthJWTBearer.encode(payload={"sub": str(edbo_id), "role": role, "scopes": scopes})

  await redis.setex(
    f"cache:user:{edbo_id}:profile",
    timedelta(minutes=settings.CACHE_EXPIRE_MINUTES).seconds,
    json.dumps(user_doc, default=str),
  )

  response = RedirectResponse(url=settings.GOOGLE_FRONTEND_REDIRECT)
  response.set_cookie(
    key="access_token",
    value=jwt_data["jwt"],
    httponly=True,
    secure=True,
    samesite="lax",
  )
  response.set_cookie(
    key="user_role",
    value=role,
    httponly=True,
    secure=True,
    samesite="lax",
  )
  return response

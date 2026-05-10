import json
from datetime import timedelta
from typing import Annotated

from api.dependencies import get_current_user, get_mongo_client, get_redis_client, limit_dependency
from core.config import settings
from core.database import MongoClient, RedisClient
from core.schemas.token import TokenBase, TokenPayload
from core.security.jwt import OAuthJWTBearer
from core.security.utils import Hash
from core.services.audit_service import write_audit_log
from crud import UserCRUD
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

router = APIRouter(tags=["Authentication"])


class ForgotPasswordRequest(BaseModel):
  email: EmailStr


class ResetPasswordRequest(BaseModel):
  token: str
  new_password: str


class EmailTokenRequest(BaseModel):
  token: str | None = None
  email: EmailStr | None = None


@router.post(
  "/login",
  status_code=status.HTTP_200_OK,
  response_model=TokenPayload,
  dependencies=[Depends(limit_dependency)],
)
async def login(
  form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
  request: Request,
):
  """
  Log in using user credentials.
  """
  # Authenticate user credentials from the MongoDB database
  users_db = mongo.get_database("users")
  if not (
    user := await UserCRUD(users_db).authenticate(
      username=form_data.username, plain_pwd=form_data.password, exclude=["_id", "password"]
    )
  ):
    await write_audit_log(
      users_db,
      action="auth.login_failed",
      actor_id=form_data.username,
      metadata={"ip": request.client.host if request.client else None},
    )
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Couldn't validate credentials",
      headers={"WWW-Authenticate": "Bearer"},
    )

  # Get data from the payload
  username, role, scopes = user.get("username"), user.get("role"), user.get("scopes")

  # Encode user payload for get an JWT
  token = OAuthJWTBearer.encode(payload={"sub": username, "role": role, "scopes": scopes})

  # Store user profile in Redis cache
  await redis.setex(
    f"cache:user:{username}:profile",
    int(timedelta(minutes=settings.CACHE_EXPIRE_MINUTES).total_seconds()),
    json.dumps(user, default=str),
  )

  return TokenPayload(access_token=token.get("jwt"), role=role)


@router.post(
  "/token",
  status_code=status.HTTP_200_OK,
  response_model=TokenPayload,
  dependencies=[Depends(get_current_user), Depends(limit_dependency)],
)
async def auth_token(
  token: Annotated[TokenBase, Header(alias="Authorization")],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  """
  Log in using an access token.
  """
  raw_token = token.access_token
  if raw_token.startswith("Bearer "):
    raw_token = raw_token[7:]

  # Decode a user's JWT
  if not (payload := OAuthJWTBearer.decode(raw_token)):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")

  # Get variables from the payload
  role, jti, exp = payload.get("role"), payload.get("jti"), payload.get("exp")

  # Check if jti is revoked
  if await OAuthJWTBearer.is_jti_in_blacklist(redis, jti=jti):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked.")

  # Add the access token to the blacklist
  if not await OAuthJWTBearer.add_jti_to_blacklist(redis, jti=jti, exp=exp):
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to add the token to the blacklist."
    )

  # Refresh token
  refresh_token = await OAuthJWTBearer.refresh(payload)

  return TokenPayload(access_token=refresh_token, role=role)


@router.post(
  "/refresh",
  status_code=status.HTTP_200_OK,
  response_model=TokenPayload,
  dependencies=[Depends(get_current_user), Depends(limit_dependency)],
)
async def refresh(
  token: Annotated[TokenBase, Header(alias="Authorization")],
  redis: Annotated[RedisClient, Depends(get_redis_client)],
):
  """Refresh an access token. Kept separate from /token for dashboard API clients."""
  return await auth_token(token=token, redis=redis)


@router.post(
  "/logout",
  status_code=status.HTTP_200_OK,
  dependencies=[Depends(get_current_user), Depends(limit_dependency)],
)
async def logout(
  token: Annotated[TokenBase, Header()], redis: Annotated[RedisClient, Depends(get_redis_client)]
):
  """
  Log out from user account.
  """
  raw_token = token.access_token
  if raw_token.startswith("Bearer "):
    raw_token = raw_token[7:]

  # Decode a user's JWT
  payload = OAuthJWTBearer.decode(token=raw_token)
  jti, exp = payload.get("jti"), payload.get("exp")

  # Check if jti is revoked
  if await OAuthJWTBearer.is_jti_in_blacklist(redis, jti=jti):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked.")

  # Add the access token to the blacklist
  if not await OAuthJWTBearer.add_jti_to_blacklist(redis, jti=jti, exp=exp):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT, detail="An error occured while adding JWT to blacklist."
    )

  return {"message": "Successfully logged out."}


@router.get("/google", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def google_login_alias():
  """OpenAPI alias for Google login. The implementation lives in google_auth.py."""
  return {"message": "Use /api/v1/auth/google/login if redirect handling is configured."}


@router.get("/google/callback", status_code=status.HTTP_200_OK)
async def google_callback_alias():
  return {"message": "Google OAuth callback endpoint is configured by google_auth.py."}


@router.post("/password/forgot", dependencies=[Depends(limit_dependency)])
async def forgot_password(
  body: ForgotPasswordRequest,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Create a password reset request placeholder without exposing account existence."""
  db = mongo.get_database("users")
  await db["password_reset_requests"].insert_one({"email": body.email, "status": "requested"})
  return {"message": "If that email exists, reset instructions will be sent."}


@router.post("/password/reset", dependencies=[Depends(limit_dependency)])
async def reset_password(
  body: ResetPasswordRequest,
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  """Reset a password using a stored reset token."""
  db = mongo.get_database("users")
  reset = await db["password_reset_requests"].find_one({"token": body.token, "status": "active"})
  if not reset:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")
  user = await UserCRUD(db).find(email=reset.get("email"))
  if not user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
  await UserCRUD(db).update(user["username"], {"password": Hash.hash(body.new_password)})
  await db["password_reset_requests"].update_one(
    {"token": body.token}, {"$set": {"status": "used"}}
  )
  return {"message": "Password reset successfully."}


@router.post("/email/verify", dependencies=[Depends(limit_dependency)])
async def verify_email(
  body: Annotated[EmailTokenRequest, Body()],
  mongo: Annotated[MongoClient, Depends(get_mongo_client)],
):
  db = mongo.get_database("users")
  verification = await db["email_verifications"].find_one({"token": body.token, "status": "active"})
  if not verification:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token"
    )
  user = await UserCRUD(db).find(email=verification.get("email"))
  if user:
    await UserCRUD(db).update(user["username"], {"email_verified": True})
  await db["email_verifications"].update_one(
    {"token": body.token}, {"$set": {"status": "used"}}
  )
  return {"message": "Email verified."}


@router.post("/email/resend-verification", dependencies=[Depends(limit_dependency)])
async def resend_email_verification(body: Annotated[EmailTokenRequest, Body()]):
  return {"message": "If that email exists, verification instructions will be sent."}

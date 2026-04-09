from authlib.integrations.starlette_client import OAuth
from core.config import settings

# Configure OAuth
google_oauth = OAuth()
google_oauth.register(
  name="google",
  client_id=settings.GOOGLE_CLIENT_ID,
  client_secret=settings.GOOGLE_CLIENT_SECRET,
  authorize_url="https://accounts.google.com/o/oauth2/auth",
  authorize_params={
    "scope": "openid email profile",
    "prompt": "select_account",
    "access_type": "offline",
  },
  access_token_url="https://oauth2.googleapis.com/token",
  client_kwargs={
    "scope": "openid email profile",
    "code_challenge_method": "S256",
  },
  server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
)

"""WebSocket routes for real-time updates."""

import asyncio
from typing import Annotated

from api.dependencies import get_jwt_payload
from core.database import RedisClient
from core.logger import logger
from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect, status

router = APIRouter(tags=["WebSockets"])


@router.websocket("/events")
async def websocket_endpoint(
  websocket: WebSocket,
  token: Annotated[str, Query(..., description="JWT for authentication")],
):
  """Establish a WebSocket connection for real-time event updates."""
  # Manually validate token since this is a WebSocket
  class MockRequest:
    def __init__(self, token):
      self.headers = {"authorization": f"Bearer {token}"}

  mock_req = MockRequest(token)
  payload = get_jwt_payload(mock_req)
  if not payload:
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return

  owner_id = payload.get("sub")
  await websocket.accept()
  logger.info(f"WebSocket connected for account: {owner_id}")

  redis = RedisClient()
  pubsub = redis.pubsub()
  channel = f"account:{owner_id}:events"
  await pubsub.subscribe(channel)

  try:
    while True:
      # Use pubsub to get messages and push to client
      message = await pubsub.get_message(ignore_subscribe_messages=True)
      if message and message["type"] == "message":
        await websocket.send_text(message["data"])
      await asyncio.sleep(0.1)  # Avoid tight loop
  except WebSocketDisconnect:
    logger.info(f"WebSocket disconnected for account: {owner_id}")
    await pubsub.unsubscribe(channel)
  except Exception as e:
    logger.error(f"WebSocket error for account {owner_id}: {str(e)}")
    await pubsub.unsubscribe(channel)
    await websocket.close()

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def mock_redis():
  from core.database import RedisClient
  
  # Create an AsyncMock for the underlying redis client
  mock_client = AsyncMock()
  mock_client.incr.return_value = 1
  
  # Set the mock client to the singleton's _client attribute
  RedisClient._client = mock_client
  
  yield mock_client
  
  # Clean up
  RedisClient._client = None


def test_device_heartbeat(client, mock_redis):
  # Mock validate_api_key to return a valid key
  from api.auth_dependencies import validate_api_key
  app.dependency_overrides[validate_api_key] = lambda: {"owner_id": "test_user", "device_id": "test_device"}

  response = client.post("/api/v1/devices/heartbeat", headers={"X-API-Key": "test_key"})

  assert response.status_code == 204
  mock_redis.setex.assert_called_once_with("device:test_user:test_device:status", 300, "online")
  
  app.dependency_overrides.clear()


def test_create_event_publishes_to_redis(client, mock_mongo_client, mock_redis):
  from api.v1.routers.events import get_event_owner
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"

  event_data = {
    "timestamp": "2026-03-18T12:34:56Z",
    "camera_id": "cam_01",
    "confidence": 0.95,
    "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
  }

  with patch("core.services.cloudinary_service.upload_base64_image", return_value="http://image.url"):
    response = client.post("/api/v1/events", json=event_data)

  assert response.status_code == 201
  assert mock_redis.publish.called
  channel = mock_redis.publish.call_args[0][0]
  assert channel == "account:test_owner:events"
  
  app.dependency_overrides.clear()


@patch("core.services.alert_service.logger")
@pytest.mark.asyncio
async def test_alert_service_spike(mock_logger, mock_redis):
  from core.services.alert_service import check_and_send_alert
  
  mock_redis.incr.return_value = 10
  
  await check_and_send_alert("test_owner", {"confidence": 0.95})
  
  assert mock_logger.warning.called
  assert "ALERT: Detection spike detected" in mock_logger.warning.call_args[0][0]
  mock_redis.delete.assert_called_with("alerts:test_owner:spike_count")

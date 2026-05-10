from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import app


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


def test_create_event_publishes_to_redis(client, mock_mongo_client, mock_redis_client):
  from api.v1.routers.events import get_event_owner

  app.dependency_overrides[get_event_owner] = lambda: "test_owner"

  event_data = {
    "timestamp": "2026-03-18T12:34:56Z",
    "camera_id": "cam_01",
    "device_id": "edge_01",
    "confidence": 0.75,
    "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
  }

  with patch(
    "core.services.cloudinary_service.upload_base64_image",
    return_value="https://example.invalid/snapshots/test-event.jpg",
  ):
    response = client.post("/api/v1/events", json=event_data)

  assert response.status_code == 201
  assert mock_redis_client.publish.called
  channel = mock_redis_client.publish.call_args[0][0]
  assert channel == "account:test_owner:events"

  app.dependency_overrides.clear()


def test_event_ingestion_requires_device_and_camera(client):
  from api.v1.routers.events import get_event_owner

  app.dependency_overrides[get_event_owner] = lambda: "test_owner"
  base_event = {
    "timestamp": "2026-03-18T12:34:56Z",
    "confidence": 0.87,
    "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
  }

  missing_device = client.post("/api/v1/events", json={**base_event, "camera_id": "barn-01-cam-a"})
  missing_camera = client.post("/api/v1/events", json={**base_event, "device_id": "edge-barn-01"})

  assert missing_device.status_code == 422
  assert missing_camera.status_code == 422

  app.dependency_overrides.clear()


def test_event_queries_filter_by_barn_device_camera_zone(client, mock_mongo_client):
  from api.v1.routers.events import get_event_owner

  app.dependency_overrides[get_event_owner] = lambda: "test_owner"
  mock_db = mock_mongo_client.get_database("barnsight")

  response = client.get(
    "/api/v1/events?barn_id=barn-01&device_id=edge-barn-01&camera_id=barn-01-cam-a&zone_id=floor-a"
  )

  assert response.status_code == 200
  query = mock_db["events"].find.call_args[0][0]
  assert query["account_id"] == "test_owner"
  assert query["barn_id"] == "barn-01"
  assert query["device_id"] == "edge-barn-01"
  assert query["camera_id"] == "barn-01-cam-a"
  assert query["zone_id"] == "floor-a"

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

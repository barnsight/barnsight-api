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


def test_device_heartbeat(client, mock_redis):
  # Mock validate_api_key to return a valid key
  from api.auth_dependencies import validate_api_key

  app.dependency_overrides[validate_api_key] = lambda: {
    "owner_id": "test_user",
    "device_id": "test_device",
  }

  response = client.post(
    "/api/v1/devices/heartbeat",
    headers={"X-API-Key": "test_key"},
    json={
      "device_id": "test_device",
      "camera_id": "cam_01",
      "status": "online",
      "camera_connected": True,
      "model_loaded": True,
      "fps": 12.5,
      "queue_size": 1,
      "queue_max_size": 100,
    },
  )

  assert response.status_code == 204
  assert mock_redis.setex.call_count == 2
  keys = {call.args[0] for call in mock_redis.setex.call_args_list}
  assert keys == {
    "camera:test_user:cam_01:status",
    "device:test_user:test_device:status",
  }

  app.dependency_overrides.clear()


def test_heartbeat_stores_device_status(client, mock_mongo_client, mock_redis):
  from api.auth_dependencies import validate_api_key

  app.dependency_overrides[validate_api_key] = lambda: {"owner_id": "test_user"}
  mock_db = mock_mongo_client.get_database("barnsight")

  response = client.post(
    "/api/v1/devices/heartbeat",
    headers={"X-API-Key": "test_key"},
    json={
      "device_id": "edge_01",
      "camera_id": "cam_01",
      "status": "degraded",
      "edge_app_version": "1.0.0",
      "model_version": "model-1",
      "queue_dropped_count": 2,
    },
  )

  assert response.status_code == 204
  mock_db["devices"].update_one.assert_called_once()
  mock_db["cameras"].update_one.assert_called_once()
  query, update = mock_db["cameras"].update_one.call_args[0]
  assert query == {"account_id": "test_user", "camera_id": "cam_01"}
  assert update["$set"]["device_id"] == "edge_01"
  assert update["$set"]["queue_dropped_count"] == 2
  device_query, device_update = mock_db["devices"].update_one.call_args[0]
  assert device_query == {"account_id": "test_user", "device_id": "edge_01"}
  assert device_update["$set"]["status"] == "degraded"

  app.dependency_overrides.clear()


def test_device_status_offline_when_redis_ttl_expired(client, mock_mongo_client, mock_redis):
  from api.v1.routers.devices import get_device_owner

  app.dependency_overrides[get_device_owner] = lambda: "test_user"
  mock_redis.get.return_value = None
  mock_db = mock_mongo_client.get_database("barnsight")
  mock_db["devices"].find_one = AsyncMock(
    return_value={
      "_id": "device_id",
      "account_id": "test_user",
      "device_id": "edge_01",
      "barn_id": "barn-1",
      "name": "Barn edge",
      "location": None,
      "status": "online",
      "last_seen_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
      "created_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
      "updated_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
    }
  )

  response = client.get("/api/v1/devices/edge_01/status")

  assert response.status_code == 200
  assert response.json()["online"] is False
  assert response.json()["status"] == "offline"

  app.dependency_overrides.clear()


def test_device_config_create_update_read(client, mock_mongo_client):
  from api.v1.routers.devices import get_device_owner

  app.dependency_overrides[get_device_owner] = lambda: "test_user"
  mock_db = mock_mongo_client.get_database("barnsight")

  response = client.put(
    "/api/v1/devices/edge_01/config",
    json={
      "enabled": True,
      "inference_fps": 4.0,
      "img_size": 640,
      "min_confidence": 0.6,
      "cooldown_seconds": 5,
      "image_cooldown_seconds": 30,
      "region_overlap_threshold": 0.25,
      "jpeg_quality": 82,
      "send_image_snapshot": True,
      "snapshot_mode": "on_detection",
      "max_image_bytes": 500000,
      "detection_zones": ["zone-a"],
    },
  )

  assert response.status_code == 200
  assert response.json()["device_id"] == "edge_01"
  assert response.json()["min_confidence"] == 0.6
  mock_db["device_configs"].update_one.assert_called_once()

  mock_db["device_configs"].find_one = AsyncMock(
    return_value={
      "_id": "cfg_id",
      "account_id": "test_user",
      "device_id": "edge_01",
      "enabled": False,
      "inference_fps": 2,
      "img_size": 640,
      "min_confidence": 0.5,
      "cooldown_seconds": 10,
      "image_cooldown_seconds": 60,
      "region_overlap_threshold": 0.3,
      "jpeg_quality": 85,
      "send_image_snapshot": True,
      "snapshot_mode": "on_detection",
      "max_image_bytes": 500000,
      "detection_zones": ["zone-a"],
      "updated_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
    }
  )

  read_response = client.get("/api/v1/devices/edge_01/config")
  assert read_response.status_code == 200
  assert read_response.json()["enabled"] is False

  app.dependency_overrides.clear()


def test_zones_can_be_created_and_fetched(client, mock_mongo_client):
  from api.v1.routers.devices import get_device_owner

  app.dependency_overrides[get_device_owner] = lambda: "test_user"
  mock_db = mock_mongo_client.get_database("barnsight")

  zone_payload = {
    "zone_id": "zone-a",
    "barn_id": "barn-1",
    "device_id": "edge_01",
    "camera_id": "cam_01",
    "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.5, "y": 0.8}],
    "enabled": True,
    "label": "Main aisle",
  }
  create_response = client.post("/api/v1/devices/zones", json=zone_payload)
  assert create_response.status_code == 201
  assert create_response.json()["zone_id"] == "zone-a"

  mock_cursor = MagicMock()
  mock_cursor.sort.return_value = mock_cursor
  mock_cursor.to_list = AsyncMock(
    return_value=[
      {
        "_id": "zone_doc",
        "account_id": "test_user",
        "created_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
        **zone_payload,
      }
    ]
  )
  mock_db["detection_zones"].find.return_value = mock_cursor

  list_response = client.get("/api/v1/devices/zones?camera_id=cam_01")
  assert list_response.status_code == 200
  assert list_response.json()[0]["label"] == "Main aisle"

  app.dependency_overrides.clear()


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
    "core.services.cloudinary_service.upload_base64_image", return_value="http://image.url"
  ):
    response = client.post("/api/v1/events", json=event_data)

  assert response.status_code == 201
  assert mock_redis_client.publish.called
  channel = mock_redis_client.publish.call_args[0][0]
  assert channel == "account:test_owner:events"

  app.dependency_overrides.clear()


def test_create_and_query_device(client, mock_mongo_client):
  from api.v1.routers.devices import get_device_owner

  app.dependency_overrides[get_device_owner] = lambda: "test_user"

  response = client.post(
    "/api/v1/devices",
    json={
      "device_id": "edge-barn-01",
      "barn_id": "barn-01",
      "name": "Barn 01 gateway",
      "location": "north wall",
    },
  )

  assert response.status_code == 201
  data = response.json()
  assert data["device_id"] == "edge-barn-01"
  assert data["barn_id"] == "barn-01"

  mock_db = mock_mongo_client.get_database("barnsight")
  mock_cursor = MagicMock()
  mock_cursor.sort.return_value = mock_cursor
  mock_cursor.to_list = AsyncMock(
    return_value=[
      {
        "_id": "dev_id",
        "account_id": "test_user",
        "device_id": "edge-barn-01",
        "barn_id": "barn-01",
        "name": "Barn 01 gateway",
        "location": "north wall",
        "status": "offline",
        "last_seen_at": None,
        "created_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
      }
    ]
  )
  mock_db["devices"].find.return_value = mock_cursor

  list_response = client.get("/api/v1/devices?barn_id=barn-01")
  assert list_response.status_code == 200
  assert list_response.json()[0]["device_id"] == "edge-barn-01"

  app.dependency_overrides.clear()


def test_create_and_query_camera_under_device(client, mock_mongo_client):
  from api.v1.routers.devices import get_device_owner

  app.dependency_overrides[get_device_owner] = lambda: "test_user"

  response = client.post(
    "/api/v1/devices/edge-barn-01/cameras",
    json={
      "camera_id": "barn-01-cam-a",
      "device_id": "edge-barn-01",
      "barn_id": "barn-01",
      "name": "Aisle A",
      "stream_label": "rtsp-redacted-a",
    },
  )

  assert response.status_code == 201
  assert response.json()["camera_id"] == "barn-01-cam-a"

  mock_db = mock_mongo_client.get_database("barnsight")
  mock_cursor = MagicMock()
  mock_cursor.sort.return_value = mock_cursor
  mock_cursor.to_list = AsyncMock(
    return_value=[
      {
        "_id": "cam_id",
        "account_id": "test_user",
        "camera_id": "barn-01-cam-a",
        "device_id": "edge-barn-01",
        "barn_id": "barn-01",
        "name": "Aisle A",
        "stream_label": "rtsp-redacted-a",
        "status": "offline",
        "last_seen_at": None,
        "created_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
      }
    ]
  )
  mock_db["cameras"].find.return_value = mock_cursor

  list_response = client.get("/api/v1/devices/edge-barn-01/cameras")
  assert list_response.status_code == 200
  assert list_response.json()[0]["device_id"] == "edge-barn-01"

  app.dependency_overrides.clear()


def test_camera_status_offline_when_heartbeat_ttl_expired(client, mock_mongo_client, mock_redis):
  from api.v1.routers.devices import get_device_owner

  app.dependency_overrides[get_device_owner] = lambda: "test_user"
  mock_redis.get.return_value = None
  mock_db = mock_mongo_client.get_database("barnsight")
  mock_db["cameras"].find_one = AsyncMock(
    return_value={
      "_id": "cam_id",
      "account_id": "test_user",
      "camera_id": "barn-01-cam-a",
      "device_id": "edge-barn-01",
      "barn_id": "barn-01",
      "name": "Aisle A",
      "stream_label": "rtsp-redacted-a",
      "status": "online",
      "last_seen_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
      "created_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
      "updated_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
    }
  )

  response = client.get("/api/v1/cameras/barn-01-cam-a/status")

  assert response.status_code == 200
  assert response.json()["online"] is False
  assert response.json()["status"] == "offline"

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


def test_camera_zones_are_camera_scoped(client, mock_mongo_client):
  from api.v1.routers.devices import get_device_owner

  app.dependency_overrides[get_device_owner] = lambda: "test_user"
  mock_db = mock_mongo_client.get_database("barnsight")
  mock_db["cameras"].find_one = AsyncMock(
    return_value={
      "_id": "cam_id",
      "account_id": "test_user",
      "camera_id": "barn-01-cam-a",
      "device_id": "edge-barn-01",
      "barn_id": "barn-01",
      "name": "Aisle A",
      "stream_label": "rtsp-redacted-a",
      "status": "offline",
      "last_seen_at": None,
      "created_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
      "updated_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
    }
  )

  response = client.post(
    "/api/v1/cameras/barn-01-cam-a/zones",
    json={
      "zone_id": "floor-a",
      "barn_id": "barn-01",
      "device_id": "edge-barn-01",
      "camera_id": "barn-01-cam-a",
      "label": "Floor A",
      "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.5, "y": 0.8}],
    },
  )

  assert response.status_code == 201
  query = mock_db["detection_zones"].update_one.call_args[0][0]
  assert query == {
    "account_id": "test_user",
    "camera_id": "barn-01-cam-a",
    "zone_id": "floor-a",
  }

  app.dependency_overrides.clear()


def test_camera_zone_cross_account_access_denied(client, mock_mongo_client):
  from api.v1.routers.devices import get_device_owner

  app.dependency_overrides[get_device_owner] = lambda: "account-a"
  mock_db = mock_mongo_client.get_database("barnsight")
  mock_db["cameras"].find_one = AsyncMock(return_value=None)

  response = client.get("/api/v1/cameras/other-account-cam/zones")

  assert response.status_code == 404
  mock_db["detection_zones"].find.assert_not_called()

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

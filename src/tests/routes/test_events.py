import base64
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from api.v1.routers.events import get_event_owner

from app.main import app


def test_create_event(client, mock_mongo_client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"

  event_data = {
    "timestamp": "2026-03-18T12:34:56Z",
    "camera_id": "cam_01",
    "device_id": "edge_01",
    "confidence": 0.87,
    "bounding_box": {"x": 120, "y": 200, "width": 80, "height": 60},
  }

  response = client.post("/api/v1/events", json=event_data)

  assert response.status_code == 201
  data = response.json()
  assert data["camera_id"] == "cam_01"
  assert data["device_id"] == "edge_01"
  assert "_id" in data


def test_create_event_accepts_edge_metadata(client, mock_mongo_client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"

  event_data = {
    "timestamp": "2026-03-18T12:34:56Z",
    "camera_id": "cam_01",
    "device_id": "edge_01",
    "confidence": 0.87,
    "bounding_box": {"x": 120, "y": 200, "width": 80, "height": 60},
    "model_version": "yolo-2026.03",
    "model_path": "/models/manure.pt",
    "img_size": 640,
    "threshold": 0.45,
    "event_id": "evt-123",
    "zone_id": "zone-a",
    "barn_id": "barn-7",
    "snapshot_mode": "on_detection",
    "edge_app_version": "1.4.2",
    "queue_latency_seconds": 1.2,
  }

  response = client.post("/api/v1/events", json=event_data)

  assert response.status_code == 201
  data = response.json()
  assert data["event_id"] == "evt-123"
  assert data["barn_id"] == "barn-7"
  assert data["queue_latency_seconds"] == 1.2


def test_create_event_rejects_invalid_confidence(client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"

  response = client.post(
    "/api/v1/events",
    json={
      "timestamp": "2026-03-18T12:34:56Z",
      "camera_id": "cam_01",
      "confidence": 1.1,
      "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
    },
  )

  assert response.status_code == 422


def test_create_event_rejects_invalid_bounding_box(client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"

  response = client.post(
    "/api/v1/events",
    json={
      "timestamp": "2026-03-18T12:34:56Z",
      "camera_id": "cam_01",
      "confidence": 0.5,
      "bounding_box": {"x": 10, "y": 10, "width": 0, "height": 50},
    },
  )

  assert response.status_code == 422


def test_create_event_rejects_oversized_snapshot(client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"
  snapshot = base64.b64encode(b"x" * 2_000_001).decode()

  response = client.post(
    "/api/v1/events",
    json={
      "timestamp": "2026-03-18T12:34:56Z",
      "camera_id": "cam_01",
      "confidence": 0.5,
      "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
      "image_snapshot": snapshot,
    },
  )

  assert response.status_code == 422


def test_create_event_deduplicates_by_event_id(client, mock_mongo_client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"
  mock_db = mock_mongo_client.get_database("barnsight")
  mock_db["events"].find_one = AsyncMock(
    return_value={
      "_id": "existing_id",
      "timestamp": datetime(2026, 3, 18, 12, 34, 56),
      "camera_id": "cam_01",
      "device_id": "edge_01",
      "confidence": 0.87,
      "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
      "event_id": "evt-123",
    }
  )

  response = client.post(
    "/api/v1/events",
    json={
      "timestamp": "2026-03-18T12:34:56Z",
      "camera_id": "cam_01",
      "device_id": "edge_01",
      "confidence": 0.87,
      "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
      "event_id": "evt-123",
    },
  )

  assert response.status_code == 201
  assert response.json()["_id"] == "existing_id"
  mock_db["events"].insert_one.assert_not_called()


def test_create_event_accepts_api_key_auth(client):
  from api.auth_dependencies import validate_api_key

  app.dependency_overrides[validate_api_key] = lambda: {"owner_id": "edge_owner"}

  response = client.post(
    "/api/v1/events",
    headers={"X-API-Key": "test_key"},
    json={
      "timestamp": "2026-03-18T12:34:56Z",
      "camera_id": "cam_01",
      "device_id": "edge_01",
      "confidence": 0.87,
      "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
    },
  )

  assert response.status_code == 201
  assert response.json()["camera_id"] == "cam_01"

  app.dependency_overrides.clear()


def test_get_events(client, mock_mongo_client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"
  mock_db = mock_mongo_client.get_database("barnsight")

  mock_events = [
    {
      "_id": "test_id_1",
      "timestamp": datetime(2026, 3, 18, 12, 34, 56),
      "camera_id": "cam_01",
      "device_id": "edge_01",
      "confidence": 0.87,
      "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50},
    }
  ]

  mock_cursor = MagicMock()
  mock_cursor.sort.return_value = mock_cursor
  mock_cursor.skip.return_value = mock_cursor
  mock_cursor.limit.return_value = mock_cursor
  mock_cursor.to_list = AsyncMock(return_value=mock_events)
  mock_db["events"].find.return_value = mock_cursor
  mock_db["events"].count_documents = AsyncMock(return_value=1)

  response = client.get("/api/v1/events?camera_id=cam_01")

  assert response.status_code == 200
  data = response.json()
  assert data["total"] == 1
  assert len(data["events"]) == 1
  assert data["events"][0]["camera_id"] == "cam_01"


def test_get_analytics(authorized_client, mock_mongo_client):
  mock_db = mock_mongo_client.get_database("barnsight")

  mock_db["events"].count_documents = AsyncMock(return_value=10)

  mock_cursor = MagicMock()
  mock_cursor.to_list = AsyncMock(
    side_effect=[
      [{"_id": None, "avg_confidence": 0.82}],
      [{"_id": "2026-03-18T12:00:00Z", "count": 10}],
      [{"_id": "2026-03-18", "count": 10}],
      [],
      [{"_id": "barn-1", "count": 10}],
      [{"_id": "zone-a", "count": 10}],
      [{"_id": "cam_01", "count": 10}],
      [{"_id": "edge_01", "count": 10}],
    ]
  )
  mock_db["events"].aggregate.return_value = mock_cursor

  response = authorized_client.get("/api/v1/analytics")

  assert response.status_code == 200
  data = response.json()
  assert data["total_detections"] == 10
  assert data["detections_per_barn"]["barn-1"] == 10
  assert data["detections_per_zone"]["zone-a"] == 10
  assert data["detections_per_camera"]["cam_01"] == 10
  assert data["detections_per_device"]["edge_01"] == 10


def test_analytics_scopes_non_admin_to_account(farmer_client, mock_mongo_client):
  mock_db = mock_mongo_client.get_database("barnsight")
  mock_db["events"].count_documents = AsyncMock(return_value=0)

  response = farmer_client.get("/api/v1/analytics")

  assert response.status_code == 200
  first_pipeline = mock_db["events"].aggregate.call_args_list[0][0][0]
  assert first_pipeline[0]["$match"]["account_id"] == "farmer"

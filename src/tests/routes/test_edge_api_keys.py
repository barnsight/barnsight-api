from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from crud.api_key_crud import ApiKeyCRUD


def _edge_key_doc(raw_key: str, scopes: list[str] | None = None) -> dict:
  crud = ApiKeyCRUD(MagicMock())
  return {
    "_id": "key_doc",
    "account_id": "acc_123",
    "farm_id": "farm_123",
    "barn_id": "barn_123",
    "device_id": "edge_001",
    "owner_id": "acc_123",
    "name": "North Barn Edge",
    "prefix": raw_key[:16],
    "key_hash": crud._hash_key(raw_key),
    "scopes": scopes
    or [
      "edge:heartbeat",
      "edge:event:create",
      "edge:snapshot:upload",
      "edge:camera:sync",
      "edge:device:config:read",
    ],
    "status": "active",
    "created_by_user_id": "admin",
    "created_at": datetime(2026, 4, 11, tzinfo=timezone.utc),
    "expires_at": None,
    "last_used_at": None,
    "last_used_ip": None,
    "revoked_at": None,
  }


def test_api_key_create_returns_raw_key_once(authorized_client, mock_mongo_client):
  response = authorized_client.post(
    "/api/v1/api-keys",
    json={
      "name": "North Barn Edge",
      "farm_id": "farm_123",
      "barn_id": "barn_123",
      "device_id": "edge_001",
      "scopes": ["edge:heartbeat", "edge:event:create"],
    },
  )

  assert response.status_code == 201
  data = response.json()
  assert data["key"].startswith("bs_live_")
  assert data["prefix"] == data["key"][:16]
  assert data["key"] != data["prefix"]

  users_db = mock_mongo_client.get_database("users")
  inserted = users_db["api_keys"].insert_one.call_args.args[0]
  assert inserted["key_hash"]
  assert "key" not in inserted
  assert inserted["device_id"] == "edge_001"


@pytest.mark.asyncio
async def test_validate_key_uses_hash_and_scope(mock_mongo_client):
  raw_key = "bs_live_test_secret"
  users_db = mock_mongo_client.get_database("users")
  cursor = MagicMock()
  cursor.to_list = AsyncMock(return_value=[_edge_key_doc(raw_key, ["edge:event:create"])])
  users_db["api_keys"].find.return_value = cursor

  key_doc = await ApiKeyCRUD(users_db).validate_key(
    raw_key, required_scope="edge:event:create", ip="127.0.0.1"
  )

  assert key_doc is not None
  assert key_doc["account_id"] == "acc_123"
  assert key_doc["farm_id"] == "farm_123"
  users_db["api_keys"].update_one.assert_called_once()


def test_edge_event_uses_key_scope_and_associations(client, mock_mongo_client):
  raw_key = "bs_live_edge_secret"
  users_db = mock_mongo_client.get_database("users")
  cursor = MagicMock()
  cursor.to_list = AsyncMock(return_value=[_edge_key_doc(raw_key)])
  users_db["api_keys"].find.return_value = cursor

  db = mock_mongo_client.get_database("barnsight")
  db["cameras"].find_one = AsyncMock(
    return_value={
      "camera_id": "camera-01",
      "account_id": "acc_123",
      "farm_id": "farm_123",
      "barn_id": "barn_123",
      "device_id": "edge_001",
    }
  )
  db["detection_zones"].find_one = AsyncMock(
    return_value={"zone_id": "zone-floor-left", "camera_id": "camera-01"}
  )

  response = client.post(
    "/api/v1/edge/events",
    headers={"X-BarnSight-Key": raw_key},
    json={
      "camera_id": "camera-01",
      "zone_id": "zone-floor-left",
      "detected_class": "manure",
      "confidence": 0.87,
      "timestamp": "2026-04-11T06:20:00Z",
      "bounding_box": {"x": 0.41, "y": 0.52, "width": 0.18, "height": 0.12},
      "model_version": "yolo-barnsight-v1",
      "inference_fps": 5.2,
      "edge_queue_size": 0,
    },
  )

  assert response.status_code == 201
  data = response.json()
  assert data["account_id"] == "acc_123"
  assert data["farm_id"] == "farm_123"
  assert data["barn_id"] == "barn_123"
  assert data["device_id"] == "edge_001"

  inserted_event = db["events"].insert_one.call_args.args[0]
  assert inserted_event["account_id"] == "acc_123"
  assert inserted_event["farm_id"] == "farm_123"
  assert inserted_event["barn_id"] == "barn_123"
  assert inserted_event["device_id"] == "edge_001"
  assert inserted_event["detected_class"] == "manure"


def test_edge_event_rejects_missing_scope(client, mock_mongo_client):
  raw_key = "bs_live_edge_secret"
  users_db = mock_mongo_client.get_database("users")
  cursor = MagicMock()
  cursor.to_list = AsyncMock(return_value=[_edge_key_doc(raw_key, ["edge:heartbeat"])])
  users_db["api_keys"].find.return_value = cursor

  response = client.post(
    "/api/v1/edge/events",
    headers={"X-BarnSight-Key": raw_key},
    json={
      "camera_id": "camera-01",
      "confidence": 0.87,
      "timestamp": "2026-04-11T06:20:00Z",
      "bounding_box": {"x": 0.41, "y": 0.52, "width": 0.18, "height": 0.12},
    },
  )

  assert response.status_code == 401

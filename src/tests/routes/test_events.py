from unittest.mock import AsyncMock, MagicMock
import pytest
from datetime import datetime
from app.main import app
from api.v1.routers.events import get_event_owner

def test_create_event(client, mock_mongo_client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"
  mock_db = mock_mongo_client.get_database("events")
  
  event_data = {
    "timestamp": "2026-03-18T12:34:56Z",
    "camera_id": "cam_01",
    "device_id": "edge_01",
    "confidence": 0.87,
    "bounding_box": {
      "x": 120,
      "y": 200,
      "width": 80,
      "height": 60
    }
  }
  
  response = client.post("/api/v1/events", json=event_data)
  
  assert response.status_code == 201
  data = response.json()
  assert data["camera_id"] == "cam_01"
  assert data["device_id"] == "edge_01"
  assert "_id" in data

def test_get_events(client, mock_mongo_client):
  app.dependency_overrides[get_event_owner] = lambda: "test_owner"
  mock_db = mock_mongo_client.get_database("events")
  
  mock_events = [
    {
      "_id": "test_id_1",
      "timestamp": datetime(2026, 3, 18, 12, 34, 56),
      "camera_id": "cam_01",
      "confidence": 0.87,
      "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 50}
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

def test_get_analytics(client, mock_mongo_client):
  mock_db = mock_mongo_client.get_database("events")
  
  mock_db["events"].count_documents = AsyncMock(return_value=10)
  
  # Mock aggregation results
  mock_camera_stats = [{"_id": "cam_01", "count": 10}]
  mock_device_stats = [{"_id": "edge_01", "count": 10}]
  
  mock_cursor = MagicMock()
  mock_cursor.to_list = AsyncMock(side_effect=[mock_camera_stats, mock_device_stats])
  mock_db["events"].aggregate = AsyncMock(return_value=mock_cursor)
  
  response = client.get("/api/v1/analytics")
  
  assert response.status_code == 200
  data = response.json()
  assert data["total_detections"] == 10
  assert data["detections_by_camera"]["cam_01"] == 10
  assert data["detections_by_device"]["edge_01"] == 10

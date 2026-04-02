from unittest.mock import AsyncMock, MagicMock
import pytest

def test_create_admin_account(client, mock_mongo_client):
  mock_db = mock_mongo_client.get_database("users")
  mock_db.list_collection_names.return_value = []
  
  response = client.post(
    "/api/v1/admin/setup",
    json={
      "username": "new_admin",
      "password": "Password123!",
      "role": "admins",
      "first_name": "Admin",
      "middle_name": "M",
      "last_name": "User",
      "account_date": "2026-03-18T12:34:56Z",
      "email": "admin@example.com"
    }
  )  
  assert response.status_code == 201
  assert response.json() == {"message": "Admin account created successfully."}

def test_admin_dashboard(authorized_client, mock_mongo_client):
  mock_users_db = mock_mongo_client.get_database("users")
  mock_barnsight_db = mock_mongo_client.get_database("barnsight")

  mock_users_db["admins"].count_documents.return_value = 1
  mock_users_db["users"].count_documents.return_value = 5
  mock_users_db["edge"].count_documents.return_value = 2
  mock_barnsight_db["events"].count_documents.return_value = 100

  response = authorized_client.get("/api/v1/admin/dashboard")
  
  assert response.status_code == 200
  data = response.json()
  assert data["users"]["admins"] == 1
  assert data["users"]["users"] == 5
  assert data["users"]["edge_devices"] == 2
  assert data["events"]["total"] == 100

def test_change_user_role(authorized_client, mock_mongo_client):
  mock_db = mock_mongo_client.get_database("users")
  mock_db.list_collection_names.return_value = ["user"]
  
  user_data = {"username": "user1", "role": "user", "scopes": ["user"]}
  mock_db["user"].find_one.return_value = user_data
  
  response = authorized_client.patch(
    "/api/v1/admin/users/user1/role",
    json={"new_role": "edge"}
  )
  
  assert response.status_code == 200
  assert response.json()["message"] == "User user1 role updated from user to edge"

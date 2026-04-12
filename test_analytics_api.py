import os
import sys

sys.path.insert(0, os.path.abspath('src'))

from fastapi.testclient import TestClient
from app.main import app
import pytest

client = TestClient(app)

def test_analytics():
    response = client.get("/api/v1/analytics?start=2026-04-05&end=2026-04-12")
    print("STATUS:", response.status_code)
    try:
        print("BODY:", response.json())
    except Exception as e:
        print("BODY (raw):", response.text)

if __name__ == "__main__":
    test_analytics()
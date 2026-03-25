from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_with_trailing_slash():
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app_env" in data


def test_health_without_trailing_slash():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app_env" in data

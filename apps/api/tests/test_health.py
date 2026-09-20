from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_returns_local_adapter_state():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "video-saas-api"
    assert payload["adapters"] == {
        "storage": "memory",
        "queue": "memory",
        "workflow": "memory",
    }

from fastapi.testclient import TestClient

from src.main import app
from src.modules.planning import ProjectRequest, run_product_flow

client = TestClient(app)

PAYLOAD = {
    "title": "Como funciona una fabrica multimodelo de video",
    "idea": "Explicar de forma visual como una solicitud se convierte en escenas, shots y un video final coordinando diferentes capacidades.",
    "duration_sec": 60,
    "aspect_ratio": "16:9",
    "audience": "creadores y equipos de producto",
    "tone": "claro y tecnologico",
    "language": "es",
}


def test_planning_api_returns_canonical_flow() -> None:
    response = client.post("/planning", json=PAYLOAD)
    assert response.status_code == 200
    expected = run_product_flow(ProjectRequest.from_dict(PAYLOAD)).to_dict()
    assert response.json() == __import__("json").loads(__import__("json").dumps(expected))
    assert response.json()["preview_plan"]["total_duration_sec"] == 60


def test_planning_api_is_deterministic() -> None:
    first = client.post("/planning", json=PAYLOAD)
    second = client.post("/planning", json=PAYLOAD)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_planning_api_maps_validation_to_422() -> None:
    response = client.post("/planning", json={**PAYLOAD, "duration_sec": 4})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item["loc"][-1] == "duration_sec" for item in detail)

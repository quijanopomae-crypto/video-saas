import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.modules.planning import ProjectRequest

client = TestClient(app)

PAYLOAD = {
    "title": "Strict planning",
    "idea": "Reject coercions and unexpected fields.",
    "duration_sec": 30,
    "aspect_ratio": "16:9",
    "audience": "test",
    "tone": "clear",
    "language": "es",
}


@pytest.mark.parametrize("value", [30.9, "30", True])
def test_duration_is_not_coerced(value):
    with pytest.raises(TypeError, match="duration_sec must be an integer"):
        ProjectRequest.from_dict({**PAYLOAD, "duration_sec": value})

    response = client.post("/planning", json={**PAYLOAD, "duration_sec": value})
    assert response.status_code == 422


def test_unexpected_fields_are_rejected():
    with pytest.raises(ValueError, match="unexpected fields"):
        ProjectRequest.from_dict({**PAYLOAD, "owner_id": "client-controlled"})

    response = client.post("/planning", json={**PAYLOAD, "owner_id": "client-controlled"})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "x" * 201),
        ("idea", "x" * 5001),
        ("audience", "x" * 201),
        ("tone", "x" * 101),
        ("language", "x" * 21),
    ],
)
def test_text_limits_are_enforced(field, value):
    response = client.post("/planning", json={**PAYLOAD, field: value})
    assert response.status_code == 422

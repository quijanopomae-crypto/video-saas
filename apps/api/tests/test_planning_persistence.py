from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

PAYLOAD = {
    "title": "Persistent planning",
    "idea": "Prove owner scoped persistence without changing canonical planning semantics.",
    "duration_sec": 30,
    "aspect_ratio": "16:9",
    "audience": "test",
    "tone": "clear",
    "language": "es",
}


def test_five_owners_are_isolated_and_identical_requests_do_not_collide() -> None:
    owners = [f"user-{index}" for index in range(1, 6)]
    stored = {}
    for owner in owners:
        response = client.post(f"/owners/{owner}/planning", json=PAYLOAD)
        assert response.status_code == 200
        stored[owner] = response.json()

    project_id = stored[owners[0]]["project_bible"]["project_id"]
    assert all(flow["project_bible"]["project_id"] == project_id for flow in stored.values())

    for owner in owners:
        response = client.get(f"/owners/{owner}/planning/{project_id}")
        assert response.status_code == 200
        assert response.json() == stored[owner]

    missing = client.get(f"/owners/not-the-owner/planning/{project_id}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "planning project not found"


def test_owner_scoped_persistence_preserves_canonical_output() -> None:
    canonical = client.post("/planning", json=PAYLOAD)
    persisted = client.post("/owners/user-preserve/planning", json=PAYLOAD)
    assert canonical.status_code == persisted.status_code == 200
    assert persisted.json() == canonical.json()


def test_blank_owner_is_rejected() -> None:
    response = client.post("/owners/%20/planning", json=PAYLOAD)
    assert response.status_code == 422
    assert response.json()["detail"] == "owner_id is required"

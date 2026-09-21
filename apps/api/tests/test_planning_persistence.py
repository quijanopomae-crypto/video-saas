from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)
PASSWORD = "correct-horse-battery-42"
PAYLOAD = {
    "title": "Persistent planning",
    "idea": "Prove authenticated owner scoped persistence without changing canonical planning semantics.",
    "duration_sec": 30,
    "aspect_ratio": "16:9",
    "audience": "test",
    "tone": "clear",
    "language": "es",
}


def identity(email: str):
    register = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert register.status_code == 201, register.text
    token = client.post("/auth/token", data={"username": email, "password": PASSWORD})
    assert token.status_code == 200, token.text
    return register.json()["user_id"], {"Authorization": f"Bearer {token.json()['access_token']}"}


def test_five_authenticated_owners_are_partitioned():
    identities = [identity(f"five-{index}@example.test") for index in range(1, 6)]
    stored = []
    for owner_id, headers in identities:
        response = client.post(f"/owners/{owner_id}/planning", json=PAYLOAD, headers=headers)
        assert response.status_code == 200
        stored.append(response.json())

    project_id = stored[0]["project_bible"]["project_id"]
    assert all(flow["project_bible"]["project_id"] == project_id for flow in stored)

    for (owner_id, headers), expected in zip(identities, stored):
        response = client.get(f"/owners/{owner_id}/planning/{project_id}", headers=headers)
        assert response.status_code == 200
        assert response.json() == expected


def test_cross_owner_read_and_upsert_are_denied_server_side():
    owner_a, headers_a = identity("owner-a@example.test")
    owner_b, headers_b = identity("owner-b@example.test")

    created = client.post(f"/owners/{owner_a}/planning", json=PAYLOAD, headers=headers_a)
    assert created.status_code == 200
    project_id = created.json()["project_bible"]["project_id"]

    # B cannot impersonate A by putting A's owner_id in the URL.
    denied_read = client.get(
        f"/owners/{owner_a}/planning/{project_id}",
        headers=headers_b,
    )
    assert denied_read.status_code == 403

    denied_update = client.post(
        f"/owners/{owner_a}/planning",
        json={**PAYLOAD, "tone": "malicious cross-owner update"},
        headers=headers_b,
    )
    assert denied_update.status_code == 403

    # A retains legitimate access to its own resource.
    own_read = client.get(
        f"/owners/{owner_a}/planning/{project_id}",
        headers=headers_a,
    )
    assert own_read.status_code == 200
    assert own_read.json() == created.json()

    # B may create its own independently partitioned resource.
    own_b = client.post(f"/owners/{owner_b}/planning", json=PAYLOAD, headers=headers_b)
    assert own_b.status_code == 200


def test_owner_scoped_endpoints_require_authentication():
    response = client.post("/owners/not-a-principal/planning", json=PAYLOAD)
    assert response.status_code == 401


def test_same_owner_same_request_is_currently_idempotent():
    owner, headers = identity("idempotent@example.test")
    first = client.post(f"/owners/{owner}/planning", json=PAYLOAD, headers=headers)
    second = client.post(f"/owners/{owner}/planning", json=PAYLOAD, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["project_bible"]["project_id"] == second.json()["project_bible"]["project_id"]
    assert first.json() == second.json()


def test_authenticated_persistence_preserves_canonical_output():
    owner, headers = identity("preserve@example.test")
    canonical = client.post("/planning", json=PAYLOAD)
    persisted = client.post(f"/owners/{owner}/planning", json=PAYLOAD, headers=headers)
    assert canonical.status_code == persisted.status_code == 200
    assert persisted.json() == canonical.json()

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)
PASSWORD = "test-only-not-valid-password-42"
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


def test_cross_owner_read_and_upsert_are_denied_bidirectionally():
    owner_a, headers_a = identity("owner-a@example.test")
    owner_b, headers_b = identity("owner-b@example.test")

    created_a = client.post(f"/owners/{owner_a}/planning", json=PAYLOAD, headers=headers_a)
    created_b = client.post(
        f"/owners/{owner_b}/planning",
        json={**PAYLOAD, "tone": "owner b canonical tone"},
        headers=headers_b,
    )
    assert created_a.status_code == created_b.status_code == 200
    project_a = created_a.json()["project_bible"]["project_id"]
    project_b = created_b.json()["project_bible"]["project_id"]

    # B -> A: read and upsert/modify are denied.
    assert client.get(
        f"/owners/{owner_a}/planning/{project_a}",
        headers=headers_b,
    ).status_code == 403
    assert client.post(
        f"/owners/{owner_a}/planning",
        json={**PAYLOAD, "tone": "b attempts a modification"},
        headers=headers_b,
    ).status_code == 403

    # A -> B: independent symmetric evidence, not inferred from middleware reuse.
    assert client.get(
        f"/owners/{owner_b}/planning/{project_b}",
        headers=headers_a,
    ).status_code == 403
    assert client.post(
        f"/owners/{owner_b}/planning",
        json={**PAYLOAD, "tone": "a attempts b modification"},
        headers=headers_a,
    ).status_code == 403

    # Both principals retain legitimate access to their own resources.
    own_a = client.get(
        f"/owners/{owner_a}/planning/{project_a}",
        headers=headers_a,
    )
    own_b = client.get(
        f"/owners/{owner_b}/planning/{project_b}",
        headers=headers_b,
    )
    assert own_a.status_code == own_b.status_code == 200
    assert own_a.json() == created_a.json()
    assert own_b.json() == created_b.json()


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

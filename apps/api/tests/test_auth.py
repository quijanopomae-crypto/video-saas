from fastapi.testclient import TestClient

from src.core.auth import verify_password
from src.main import app
from src.modules.auth.persistence import load_user_by_email

client = TestClient(app)
PASSWORD = "correct-horse-battery-42"


def register_and_login(email: str):
    registered = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert registered.status_code == 201, registered.text
    user = registered.json()
    token = client.post(
        "/auth/token",
        data={"username": email, "password": PASSWORD},
    )
    assert token.status_code == 200, token.text
    return user, {"Authorization": f"Bearer {token.json()['access_token']}"}


def test_password_is_hashed_and_bearer_identity_is_verifiable():
    user, headers = register_and_login("hash-check@example.test")
    stored = load_user_by_email("hash-check@example.test")
    assert stored is not None
    assert stored["password_hash"] != PASSWORD
    assert PASSWORD not in str(stored["password_hash"])
    assert verify_password(PASSWORD, str(stored["password_hash"]))

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == user


def test_invalid_credentials_and_unauthenticated_access_are_rejected():
    register_and_login("reject@example.test")
    bad = client.post(
        "/auth/token",
        data={"username": "reject@example.test", "password": "wrong-password-123"},
    )
    assert bad.status_code == 401

    missing = client.get("/auth/me")
    assert missing.status_code == 401


def test_duplicate_email_is_rejected_without_exposing_password():
    first = client.post(
        "/auth/register",
        json={"email": "duplicate@example.test", "password": PASSWORD},
    )
    second = client.post(
        "/auth/register",
        json={"email": "DUPLICATE@example.test", "password": PASSWORD},
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert PASSWORD not in second.text

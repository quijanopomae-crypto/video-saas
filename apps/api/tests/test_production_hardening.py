from fastapi.testclient import TestClient

from src.core.config import Settings
from src.main import create_app


def test_production_disables_swagger_redoc_and_openapi_schema():
    settings = Settings(app_env="production", _env_file=None)
    client = TestClient(create_app(settings))
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_test_environment_keeps_openapi_available():
    settings = Settings(
        app_env="test",
        auth_jwt_secret="test-only-secret-not-valid-for-production-0123456789",
        _env_file=None,
    )
    client = TestClient(create_app(settings))
    assert client.get("/openapi.json").status_code == 200

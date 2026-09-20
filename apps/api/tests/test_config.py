from src.core.config import Settings


def test_default_configuration_is_local_only():
    settings = Settings(_env_file=None)
    assert settings.storage_backend == "memory"
    assert settings.queue_backend == "memory"
    assert settings.workflow_backend == "memory"
    assert "127.0.0.1" in settings.database_url

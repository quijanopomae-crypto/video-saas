from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://video_saas:video_saas@127.0.0.1:5432/video_saas"
    cors_origins: str = "http://localhost:3000"
    storage_backend: str = "memory"
    queue_backend: str = "memory"
    workflow_backend: str = "memory"
    auth_jwt_secret: str = ""
    auth_jwt_issuer: str = "video-saas"
    auth_jwt_audience: str = "video-saas-users"
    auth_access_token_minutes: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

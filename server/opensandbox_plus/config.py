from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AppRole = Literal["all", "api", "worker"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OSB_PLUS_",
        extra="ignore",
    )

    app_role: AppRole = "all"
    public_base_url: str = "http://localhost:8080"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080"])

    database_url: str = (
        "postgresql+asyncpg://opensandbox_plus:opensandbox_plus@localhost:5432/opensandbox_plus"
    )
    redis_url: str = "redis://localhost:6379/0"

    console_static_dir: str = "opensandbox_plus/static/console"
    background_jobs_enabled: bool = True

    casdoor_issuer: str = "http://localhost:8000"
    casdoor_audience: str = "osb-console"
    casdoor_discovery_url: str | None = None
    casdoor_jwks_url: str | None = None
    casdoor_admin_client_id: str = "osb-plus-admin"
    casdoor_admin_client_secret: str | None = None

    credential_secret_pepper: str = "dev-change-me"
    credential_default_expires_days: int = 180
    credential_max_expires_days: int = 180
    credential_max_keys_per_user: int = 10

    image_upload_dir: str = "var/opensandbox-plus/images"
    image_upload_max_bytes: int = 5 * 1024 * 1024 * 1024

    opensandbox_default_backend_id: str = "backend_local"
    opensandbox_default_backend_name: str = "local-opensandbox"
    opensandbox_default_backend_base_url: str = "http://opensandbox:8090"
    opensandbox_internal_api_key: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()

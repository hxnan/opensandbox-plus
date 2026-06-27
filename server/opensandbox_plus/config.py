from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppRole = Literal["all", "api", "worker"]
DeploymentEnv = Literal["development", "staging", "production"]

_WEAK_SECRET_VALUES = {
    "",
    "change-me",
    "change-me-credential-pepper",
    "change-me-internal-opensandbox-key",
    "dev-change-me",
    "secret",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OSB_PLUS_",
        extra="ignore",
    )

    deployment_env: DeploymentEnv = "development"
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

    @model_validator(mode="after")
    def validate_production_baseline(self) -> "Settings":
        if self.deployment_env != "production":
            return self

        errors: list[str] = []
        if self.public_base_url.startswith("http://"):
            errors.append("OSB_PLUS_PUBLIC_BASE_URL must use https in production")
        if self.casdoor_issuer.startswith("http://"):
            errors.append("OSB_PLUS_CASDOOR_ISSUER must use https in production")
        if _is_weak_secret(self.credential_secret_pepper):
            errors.append("OSB_PLUS_CREDENTIAL_SECRET_PEPPER must be a strong production secret")
        if _is_weak_secret(self.opensandbox_internal_api_key):
            errors.append("OSB_PLUS_OPENSANDBOX_INTERNAL_API_KEY must be a strong production secret")
        if self.casdoor_admin_client_secret is not None and _is_weak_secret(
            self.casdoor_admin_client_secret
        ):
            errors.append("OSB_PLUS_CASDOOR_ADMIN_CLIENT_SECRET must not use a weak default")

        if errors:
            raise ValueError("; ".join(errors))
        return self


def _is_weak_secret(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized in _WEAK_SECRET_VALUES or len(normalized) < 32


@lru_cache
def get_settings() -> Settings:
    return Settings()

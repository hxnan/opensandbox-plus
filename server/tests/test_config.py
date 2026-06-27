import pytest
from pydantic import ValidationError

from opensandbox_plus.config import Settings


def test_development_allows_local_defaults() -> None:
    settings = Settings()

    assert settings.deployment_env == "development"
    assert settings.public_base_url == "http://localhost:8080"


def test_production_rejects_weak_defaults() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(deployment_env="production")

    message = str(exc_info.value)
    assert "OSB_PLUS_PUBLIC_BASE_URL must use https" in message
    assert "OSB_PLUS_CASDOOR_ISSUER must use https" in message
    assert "OSB_PLUS_CREDENTIAL_SECRET_PEPPER" in message
    assert "OSB_PLUS_OPENSANDBOX_INTERNAL_API_KEY" in message


def test_production_accepts_explicit_secure_baseline() -> None:
    settings = Settings(
        deployment_env="production",
        public_base_url="https://sandbox.example.com",
        casdoor_issuer="https://identity.example.com",
        credential_secret_pepper="prod-credential-pepper-with-32-plus-chars",
        opensandbox_internal_api_key="prod-opensandbox-api-key-with-32-plus-chars",
        casdoor_admin_client_secret="prod-casdoor-admin-secret-with-32-plus-chars",
    )

    assert settings.deployment_env == "production"

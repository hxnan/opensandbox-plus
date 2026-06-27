from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from opensandbox_plus.auth.jwt import CasdoorTokenVerifier, TokenValidationError
from opensandbox_plus.auth.principal import CloudSandboxPrincipal
from opensandbox_plus.config import Settings
from opensandbox_plus.credentials.service import (
    CredentialServiceError,
    _validate_credential_and_user,
)
from opensandbox_plus.sandboxes import service as sandbox_service


def test_disabled_cloud_sandbox_credential_is_rejected() -> None:
    credential = _credential(status="disabled")
    user = _user()

    with pytest.raises(CredentialServiceError) as exc_info:
        _validate_credential_and_user(credential, user)

    assert exc_info.value.code == "INVALID_CLOUD_SANDBOX_CREDENTIAL"
    assert exc_info.value.status_code == 401


def test_expired_cloud_sandbox_credential_is_rejected() -> None:
    credential = _credential(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    user = _user()

    with pytest.raises(CredentialServiceError) as exc_info:
        _validate_credential_and_user(credential, user)

    assert exc_info.value.code == "INVALID_CLOUD_SANDBOX_CREDENTIAL"
    assert exc_info.value.status_code == 401


def test_disabled_user_cannot_use_valid_cloud_sandbox_credential() -> None:
    credential = _credential()
    user = _user(status="disabled")

    with pytest.raises(CredentialServiceError) as exc_info:
        _validate_credential_and_user(credential, user)

    assert exc_info.value.code == "FORBIDDEN"
    assert exc_info.value.status_code == 403


def test_user_without_opensandbox_role_cannot_use_cloud_sandbox_credential() -> None:
    credential = _credential()
    user = _user(roles=["casdoor_user"])

    with pytest.raises(CredentialServiceError) as exc_info:
        _validate_credential_and_user(credential, user)

    assert exc_info.value.code == "FORBIDDEN"
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cross_user_sandbox_lookup_is_not_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup_calls: list[tuple[str, str]] = []

    async def fake_get_owned_sandbox(session, *, owner_subject_id: str, public_sandbox_id: str):
        lookup_calls.append((owner_subject_id, public_sandbox_id))
        return None

    monkeypatch.setattr(sandbox_service, "get_owned_sandbox", fake_get_owned_sandbox)
    principal = CloudSandboxPrincipal(
        principal=_principal("casdoor:built-in:alice"),
        credential_id="cred_alice",
        public_prefix="alice1",
    )

    with pytest.raises(HTTPException) as exc_info:
        await sandbox_service.ensure_owned_sandbox(
            object(),
            principal=principal,
            sandbox_id="sbx_bob",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "NOT_FOUND"
    assert lookup_calls == [("casdoor:built-in:alice", "sbx_bob")]


def test_casdoor_token_verifier_rejects_wrong_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = CasdoorTokenVerifier(_jwt_settings())
    verifier._jwks_client = _FakeJwksClient()  # type: ignore[assignment]

    def fake_decode(*args, **kwargs):
        raise jwt.InvalidAudienceError("audience mismatch")

    monkeypatch.setattr(jwt, "decode", fake_decode)

    with pytest.raises(TokenValidationError) as exc_info:
        verifier.verify("header.payload.signature")

    assert "audience mismatch" in str(exc_info.value)


def test_casdoor_token_verifier_rejects_wrong_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = CasdoorTokenVerifier(_jwt_settings())
    verifier._jwks_client = _FakeJwksClient()  # type: ignore[assignment]

    def fake_decode(*args, **kwargs):
        raise jwt.InvalidIssuerError("issuer mismatch")

    monkeypatch.setattr(jwt, "decode", fake_decode)

    with pytest.raises(TokenValidationError) as exc_info:
        verifier.verify("header.payload.signature")

    assert "issuer mismatch" in str(exc_info.value)


def _credential(
    *,
    status: str = "active",
    expires_at: datetime | None = None,
):
    return SimpleNamespace(
        status=status,
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=1),
    )


def _user(
    *,
    status: str = "active",
    roles: list[str] | None = None,
):
    return SimpleNamespace(
        subject_id="casdoor:built-in:alice",
        casdoor_owner="built-in",
        casdoor_user="alice",
        username="alice",
        email="alice@example.com",
        display_name="Alice",
        status=status,
        roles=roles if roles is not None else ["osb_agent_user"],
    )


def _principal(subject_id: str):
    return SimpleNamespace(
        subject_id=subject_id,
        casdoor_owner="built-in",
        casdoor_user="alice",
        username="alice",
        email="alice@example.com",
        display_name="Alice",
        status="active",
        roles=["osb_agent_user"],
    )


def _jwt_settings() -> Settings:
    return Settings(
        casdoor_issuer="https://identity.example.com",
        casdoor_audience="osb-console",
        casdoor_jwks_url="https://identity.example.com/.well-known/jwks",
        background_jobs_enabled=False,
    )


class _FakeSigningKey:
    key = "fake-public-key"


class _FakeJwksClient:
    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        assert token == "header.payload.signature"
        return _FakeSigningKey()

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.auth.principal import CloudSandboxPrincipal
from opensandbox_plus.config import Settings
from opensandbox_plus.credentials.crypto import (
    generate_credential,
    hash_credential_key,
    parse_credential_key,
)
from opensandbox_plus.credentials.repository import (
    count_active_credentials,
    create_credential,
    get_credential_with_owner_by_hash,
    get_owned_credential,
    list_credentials,
    list_credentials_for_owner,
    touch_credential_usage,
    update_credential_secret,
    update_credential_status,
    update_credential_status_by_id,
)
from opensandbox_plus.db.models import CloudSandboxCredential
from opensandbox_plus.db.models import UserIdentity


class CredentialServiceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class IssuedCredential:
    credential: CloudSandboxCredential
    key: str


async def issue_credential(
    session: AsyncSession,
    *,
    settings: Settings,
    principal: Principal,
    name: str,
    agent_id: str | None,
    expires_in_days: int | None,
) -> IssuedCredential:
    active_count = await count_active_credentials(session, principal.subject_id)
    if active_count >= settings.credential_max_keys_per_user:
        raise CredentialServiceError(
            "QUOTA_EXCEEDED",
            "active cloud sandbox credential limit exceeded",
            429,
        )

    days = expires_in_days or settings.credential_default_expires_days
    if days > settings.credential_max_expires_days:
        raise CredentialServiceError(
            "INVALID_REQUEST",
            "expires_in_days exceeds configured maximum",
            400,
        )

    generated = generate_credential(settings.credential_secret_pepper)
    expires_at = datetime.now(UTC) + timedelta(days=days)
    try:
        credential = await create_credential(
            session,
            credential_id=f"cred_{uuid4().hex}",
            owner_subject_id=principal.subject_id,
            name=name,
            public_prefix=generated.public_prefix,
            key_hash=generated.key_hash,
            expires_at=expires_at,
            issued_by_agent_id=agent_id,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise CredentialServiceError(
            "CONFLICT",
            "credential name or prefix already exists",
            409,
        ) from exc

    return IssuedCredential(credential=credential, key=generated.key)


async def list_owned_credentials(
    session: AsyncSession,
    *,
    principal: Principal,
    page: int,
    page_size: int,
) -> tuple[list[CloudSandboxCredential], int]:
    return await list_credentials(
        session,
        owner_subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
    )


async def list_user_credentials_for_admin(
    session: AsyncSession,
    *,
    owner_subject_id: str,
    page: int,
    page_size: int,
) -> tuple[list[CloudSandboxCredential], int]:
    return await list_credentials_for_owner(
        session,
        owner_subject_id=owner_subject_id,
        page=page,
        page_size=page_size,
    )


async def disable_credential_for_admin(
    session: AsyncSession,
    *,
    credential_id: str,
) -> CloudSandboxCredential:
    credential = await update_credential_status_by_id(
        session,
        credential_id=credential_id,
        status="disabled",
    )
    if credential is None:
        raise CredentialServiceError("NOT_FOUND", "credential not found", 404)
    return credential


async def disable_owned_credential(
    session: AsyncSession,
    *,
    principal: Principal,
    credential_id: str,
) -> CloudSandboxCredential:
    credential = await update_credential_status(
        session,
        owner_subject_id=principal.subject_id,
        credential_id=credential_id,
        status="disabled",
    )
    if credential is None:
        raise CredentialServiceError("NOT_FOUND", "credential not found", 404)
    return credential


async def revoke_owned_credential(
    session: AsyncSession,
    *,
    principal: Principal,
    credential_id: str,
) -> CloudSandboxCredential:
    credential = await update_credential_status(
        session,
        owner_subject_id=principal.subject_id,
        credential_id=credential_id,
        status="revoked",
    )
    if credential is None:
        raise CredentialServiceError("NOT_FOUND", "credential not found", 404)
    return credential


async def rotate_owned_credential(
    session: AsyncSession,
    *,
    settings: Settings,
    principal: Principal,
    credential_id: str,
) -> IssuedCredential:
    existing = await get_owned_credential(
        session,
        owner_subject_id=principal.subject_id,
        credential_id=credential_id,
    )
    if existing is None:
        raise CredentialServiceError("NOT_FOUND", "credential not found", 404)

    generated = generate_credential(settings.credential_secret_pepper)
    try:
        credential = await update_credential_secret(
            session,
            owner_subject_id=principal.subject_id,
            credential_id=credential_id,
            public_prefix=generated.public_prefix,
            key_hash=generated.key_hash,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise CredentialServiceError("CONFLICT", "credential prefix already exists", 409) from exc

    if credential is None:
        raise CredentialServiceError("NOT_FOUND", "credential not found", 404)
    return IssuedCredential(credential=credential, key=generated.key)


async def verify_cloud_sandbox_credential(
    session: AsyncSession,
    *,
    settings: Settings,
    raw_key: str,
    client_ip: str | None,
) -> CloudSandboxPrincipal:
    try:
        parsed = parse_credential_key(raw_key)
    except ValueError as exc:
        raise CredentialServiceError(
            "INVALID_CLOUD_SANDBOX_CREDENTIAL",
            "invalid cloud sandbox credential",
            401,
        ) from exc

    key_hash = hash_credential_key(parsed.raw_key, settings.credential_secret_pepper)
    row = await get_credential_with_owner_by_hash(
        session,
        public_prefix=parsed.public_prefix,
        key_hash=key_hash,
    )
    if row is None:
        raise CredentialServiceError(
            "INVALID_CLOUD_SANDBOX_CREDENTIAL",
            "invalid cloud sandbox credential",
            401,
        )

    credential, user = row
    _validate_credential_and_user(credential, user)
    await touch_credential_usage(session, credential_id=credential.id, ip=client_ip)
    return CloudSandboxPrincipal(
        principal=_principal_from_user_identity(user),
        credential_id=credential.id,
        public_prefix=credential.public_prefix,
    )


def _validate_credential_and_user(
    credential: CloudSandboxCredential,
    user: UserIdentity,
) -> None:
    if credential.status != "active":
        raise CredentialServiceError(
            "INVALID_CLOUD_SANDBOX_CREDENTIAL",
            "cloud sandbox credential is not active",
            401,
        )

    if credential.expires_at is not None:
        expires_at = credential.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise CredentialServiceError(
                "INVALID_CLOUD_SANDBOX_CREDENTIAL",
                "cloud sandbox credential is expired",
                401,
            )

    if user.status != "active":
        raise CredentialServiceError("FORBIDDEN", "user is not active", 403)

    if "osb_agent_user" not in user.roles and "osb_platform_admin" not in user.roles:
        raise CredentialServiceError(
            "FORBIDDEN",
            "user does not have OpenSandbox Plus role",
            403,
        )


def _principal_from_user_identity(user: UserIdentity) -> Principal:
    return Principal(
        subject_id=user.subject_id,
        casdoor_owner=user.casdoor_owner,
        casdoor_user=user.casdoor_user,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        roles=list(user.roles or []),
        status=user.status,
    )

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.db.models import CloudSandboxCredential, UserIdentity


async def count_active_credentials(session: AsyncSession, owner_subject_id: str) -> int:
    now = datetime.now(UTC)
    stmt = (
        select(func.count())
        .select_from(CloudSandboxCredential)
        .where(
            CloudSandboxCredential.owner_subject_id == owner_subject_id,
            CloudSandboxCredential.status == "active",
            or_(
                CloudSandboxCredential.expires_at.is_(None),
                CloudSandboxCredential.expires_at > now,
            ),
        )
    )
    return int(await session.scalar(stmt) or 0)


async def create_credential(
    session: AsyncSession,
    *,
    credential_id: str,
    owner_subject_id: str,
    name: str,
    public_prefix: str,
    key_hash: str,
    expires_at: datetime | None,
    issued_by_agent_id: str | None,
) -> CloudSandboxCredential:
    now = datetime.now(UTC)
    credential = CloudSandboxCredential(
        id=credential_id,
        owner_subject_id=owner_subject_id,
        name=name,
        public_prefix=public_prefix,
        key_hash=key_hash,
        hash_algorithm="hmac-sha256",
        status="active",
        expires_at=expires_at,
        issued_by_agent_id=issued_by_agent_id,
        created_at=now,
        updated_at=now,
    )
    session.add(credential)
    await session.flush()
    await session.commit()
    return credential


async def list_credentials(
    session: AsyncSession,
    *,
    owner_subject_id: str,
    page: int,
    page_size: int,
) -> tuple[list[CloudSandboxCredential], int]:
    where = CloudSandboxCredential.owner_subject_id == owner_subject_id
    total = int(
        await session.scalar(select(func.count()).select_from(CloudSandboxCredential).where(where))
        or 0
    )
    stmt: Select[tuple[CloudSandboxCredential]] = (
        select(CloudSandboxCredential)
        .where(where)
        .order_by(CloudSandboxCredential.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = await session.scalars(stmt)
    return list(rows), total


async def list_credentials_for_owner(
    session: AsyncSession,
    *,
    owner_subject_id: str,
    page: int,
    page_size: int,
) -> tuple[list[CloudSandboxCredential], int]:
    return await list_credentials(
        session,
        owner_subject_id=owner_subject_id,
        page=page,
        page_size=page_size,
    )


async def get_owned_credential(
    session: AsyncSession,
    *,
    owner_subject_id: str,
    credential_id: str,
) -> CloudSandboxCredential | None:
    stmt = select(CloudSandboxCredential).where(
        CloudSandboxCredential.id == credential_id,
        CloudSandboxCredential.owner_subject_id == owner_subject_id,
    )
    return await session.scalar(stmt)


async def update_credential_secret(
    session: AsyncSession,
    *,
    owner_subject_id: str,
    credential_id: str,
    public_prefix: str,
    key_hash: str,
) -> CloudSandboxCredential | None:
    now = datetime.now(UTC)
    stmt = (
        update(CloudSandboxCredential)
        .where(
            CloudSandboxCredential.id == credential_id,
            CloudSandboxCredential.owner_subject_id == owner_subject_id,
        )
        .values(
            public_prefix=public_prefix,
            key_hash=key_hash,
            status="active",
            revoked_at=None,
            updated_at=now,
        )
        .returning(CloudSandboxCredential)
    )
    credential = await session.scalar(stmt)
    await session.commit()
    return credential


async def update_credential_status(
    session: AsyncSession,
    *,
    owner_subject_id: str,
    credential_id: str,
    status: str,
) -> CloudSandboxCredential | None:
    now = datetime.now(UTC)
    values: dict[str, object] = {"status": status, "updated_at": now}
    if status in {"disabled", "revoked"}:
        values["revoked_at"] = now
    stmt = (
        update(CloudSandboxCredential)
        .where(
            CloudSandboxCredential.id == credential_id,
            CloudSandboxCredential.owner_subject_id == owner_subject_id,
        )
        .values(**values)
        .returning(CloudSandboxCredential)
    )
    credential = await session.scalar(stmt)
    await session.commit()
    return credential


async def update_credential_status_by_id(
    session: AsyncSession,
    *,
    credential_id: str,
    status: str,
) -> CloudSandboxCredential | None:
    now = datetime.now(UTC)
    values: dict[str, object] = {"status": status, "updated_at": now}
    if status in {"disabled", "revoked"}:
        values["revoked_at"] = now
    stmt = (
        update(CloudSandboxCredential)
        .where(CloudSandboxCredential.id == credential_id)
        .values(**values)
        .returning(CloudSandboxCredential)
    )
    credential = await session.scalar(stmt)
    await session.commit()
    return credential


async def get_credential_with_owner_by_hash(
    session: AsyncSession,
    *,
    public_prefix: str,
    key_hash: str,
) -> tuple[CloudSandboxCredential, UserIdentity] | None:
    stmt = (
        select(CloudSandboxCredential, UserIdentity)
        .join(UserIdentity, UserIdentity.subject_id == CloudSandboxCredential.owner_subject_id)
        .where(
            CloudSandboxCredential.public_prefix == public_prefix,
            CloudSandboxCredential.key_hash == key_hash,
        )
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    credential, user = row
    return credential, user


async def touch_credential_usage(
    session: AsyncSession,
    *,
    credential_id: str,
    ip: str | None,
) -> None:
    stmt = (
        update(CloudSandboxCredential)
        .where(CloudSandboxCredential.id == credential_id)
        .values(last_used_at=datetime.now(UTC), last_used_ip=ip)
    )
    await session.execute(stmt)
    await session.commit()

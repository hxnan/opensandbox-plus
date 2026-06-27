from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.db.models import CloudSandboxCredential, Sandbox, UserIdentity


async def upsert_user_identity(session: AsyncSession, principal: Principal) -> UserIdentity:
    values = {
        "subject_id": principal.subject_id,
        "casdoor_owner": principal.casdoor_owner,
        "casdoor_user": principal.casdoor_user,
        "username": principal.username,
        "email": principal.email,
        "display_name": principal.display_name,
        "status": principal.status,
        "roles": principal.roles,
    }
    stmt = (
        insert(UserIdentity)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[UserIdentity.subject_id],
            set_={
                "casdoor_owner": principal.casdoor_owner,
                "casdoor_user": principal.casdoor_user,
                "username": principal.username,
                "email": principal.email,
                "display_name": principal.display_name,
                "status": principal.status,
                "roles": principal.roles,
                "updated_at": func.now(),
            },
        )
        .returning(UserIdentity)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


async def list_user_identities(
    session: AsyncSession,
    *,
    keyword: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[UserIdentity], int]:
    stmt: Select[tuple[UserIdentity]] = select(UserIdentity)
    count_stmt = select(func.count()).select_from(UserIdentity)
    filters = []

    if status is not None:
        filters.append(UserIdentity.status == status)
    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            or_(
                UserIdentity.subject_id.ilike(pattern),
                UserIdentity.username.ilike(pattern),
                UserIdentity.email.ilike(pattern),
                UserIdentity.display_name.ilike(pattern),
            )
        )

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    stmt = (
        stmt.order_by(UserIdentity.updated_at.desc(), UserIdentity.subject_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = await session.scalars(stmt)
    total = int(await session.scalar(count_stmt) or 0)
    return list(rows), total


async def active_credential_counts_by_user(
    session: AsyncSession,
    *,
    subject_ids: list[str],
) -> dict[str, int]:
    if not subject_ids:
        return {}
    now = datetime.now(UTC)
    stmt = (
        select(CloudSandboxCredential.owner_subject_id, func.count())
        .where(
            CloudSandboxCredential.owner_subject_id.in_(subject_ids),
            CloudSandboxCredential.status == "active",
            or_(
                CloudSandboxCredential.expires_at.is_(None),
                CloudSandboxCredential.expires_at > now,
            ),
        )
        .group_by(CloudSandboxCredential.owner_subject_id)
    )
    rows = await session.execute(stmt)
    return {subject_id: int(count) for subject_id, count in rows.all()}


async def active_sandbox_counts_by_user(
    session: AsyncSession,
    *,
    subject_ids: list[str],
) -> dict[str, int]:
    if not subject_ids:
        return {}
    stmt = (
        select(Sandbox.owner_subject_id, func.count())
        .where(
            Sandbox.owner_subject_id.in_(subject_ids),
            Sandbox.state.in_(("pending", "running", "paused", "stopping", "unknown")),
        )
        .group_by(Sandbox.owner_subject_id)
    )
    rows = await session.execute(stmt)
    return {subject_id: int(count) for subject_id, count in rows.all()}

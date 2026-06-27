from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.db.models import AuditEvent, CloudSandboxCredential, RuntimeBackend, Sandbox


async def list_backends(session: AsyncSession) -> list[RuntimeBackend]:
    rows = await session.scalars(select(RuntimeBackend).order_by(RuntimeBackend.name))
    return list(rows)


async def update_backend_health(
    session: AsyncSession,
    *,
    backend_id: str,
    health_status: str,
    last_error: str | None,
) -> None:
    stmt = (
        update(RuntimeBackend)
        .where(RuntimeBackend.id == backend_id)
        .values(
            health_status=health_status,
            last_checked_at=datetime.now(UTC),
            last_error=last_error,
            updated_at=datetime.now(UTC),
        )
    )
    await session.execute(stmt)
    await session.commit()


async def count_active_credentials(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(CloudSandboxCredential)
        .where(CloudSandboxCredential.status == "active")
    )
    return int(await session.scalar(stmt) or 0)


async def count_running_sandboxes(session: AsyncSession) -> int:
    stmt = select(func.count()).select_from(Sandbox).where(Sandbox.state == "running")
    return int(await session.scalar(stmt) or 0)


async def sandbox_state_distribution(session: AsyncSession) -> dict[str, int]:
    stmt = select(Sandbox.state, func.count()).group_by(Sandbox.state)
    rows = await session.execute(stmt)
    return {state: int(count) for state, count in rows.all()}


async def running_sandbox_count_by_backend(session: AsyncSession) -> dict[str, int]:
    stmt = (
        select(Sandbox.runtime_backend_id, func.count())
        .where(Sandbox.state == "running")
        .group_by(Sandbox.runtime_backend_id)
    )
    rows = await session.execute(stmt)
    return {backend_id: int(count) for backend_id, count in rows.all()}


async def count_failed_sandboxes_15m(session: AsyncSession) -> int:
    since = datetime.now(UTC) - timedelta(minutes=15)
    stmt = (
        select(func.count())
        .select_from(Sandbox)
        .where(Sandbox.state == "failed", Sandbox.updated_at >= since)
    )
    return int(await session.scalar(stmt) or 0)


async def count_recent_backend_errors_15m(session: AsyncSession) -> int:
    since = datetime.now(UTC) - timedelta(minutes=15)
    stmt = (
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.created_at >= since,
            AuditEvent.error_code.in_(["OPENSANDBOX_BACKEND_ERROR", "NO_HEALTHY_BACKEND"]),
        )
    )
    return int(await session.scalar(stmt) or 0)

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.config import Settings
from opensandbox_plus.db.models import RuntimeBackend, Sandbox


async def ensure_default_backend(session: AsyncSession, settings: Settings) -> RuntimeBackend:
    stmt = (
        insert(RuntimeBackend)
        .values(
            id=settings.opensandbox_default_backend_id,
            name=settings.opensandbox_default_backend_name,
            kind="docker",
            status="active",
            health_status="unknown",
            opensandbox_base_url=settings.opensandbox_default_backend_base_url,
            api_key_env="OSB_PLUS_OPENSANDBOX_INTERNAL_API_KEY",
            weight=100,
            capabilities={},
            metadata_={},
        )
        .on_conflict_do_update(
            index_elements=[RuntimeBackend.id],
            set_={
                "name": settings.opensandbox_default_backend_name,
                "opensandbox_base_url": settings.opensandbox_default_backend_base_url,
                "api_key_env": "OSB_PLUS_OPENSANDBOX_INTERNAL_API_KEY",
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(RuntimeBackend)
    )
    backend = await session.scalar(stmt)
    await session.flush()
    if backend is None:
        raise RuntimeError("failed to initialize default OpenSandbox backend")
    return backend


async def create_sandbox_index(
    session: AsyncSession,
    *,
    settings: Settings,
    public_sandbox_id: str,
    opensandbox_id: str,
    owner_subject_id: str,
    credential_id: str,
    image: str | None,
    state: str,
    requested_timeout_seconds: int | None,
    expires_at: datetime | None,
    payload: dict[str, Any],
) -> Sandbox:
    await ensure_default_backend(session, settings)
    now = datetime.now(UTC)
    sandbox = Sandbox(
        id=f"sbxidx_{opensandbox_id}",
        public_sandbox_id=public_sandbox_id,
        opensandbox_id=opensandbox_id,
        owner_subject_id=owner_subject_id,
        created_by_credential_id=credential_id,
        runtime_backend_id=settings.opensandbox_default_backend_id,
        runtime_profile_id=None,
        image=image,
        state=state,
        requested_timeout_seconds=requested_timeout_seconds,
        expires_at=expires_at,
        last_opensandbox_payload=payload,
        created_at=now,
        updated_at=now,
    )
    session.add(sandbox)
    await session.commit()
    return sandbox


async def list_owned_sandbox_ids(
    session: AsyncSession,
    *,
    owner_subject_id: str,
) -> set[str]:
    stmt = select(Sandbox.public_sandbox_id).where(Sandbox.owner_subject_id == owner_subject_id)
    return set(await session.scalars(stmt))


async def get_owned_sandbox(
    session: AsyncSession,
    *,
    owner_subject_id: str,
    public_sandbox_id: str,
) -> Sandbox | None:
    stmt: Select[tuple[Sandbox]] = select(Sandbox).where(
        Sandbox.owner_subject_id == owner_subject_id,
        Sandbox.public_sandbox_id == public_sandbox_id,
    )
    return await session.scalar(stmt)


async def mark_sandbox_deleted(
    session: AsyncSession,
    *,
    sandbox: Sandbox,
    payload: dict[str, Any] | None = None,
) -> None:
    stmt = (
        update(Sandbox)
        .where(Sandbox.id == sandbox.id)
        .values(
            state="deleted",
            terminated_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            last_opensandbox_payload=payload or sandbox.last_opensandbox_payload,
        )
    )
    await session.execute(stmt)
    await session.commit()


async def update_sandbox_index(
    session: AsyncSession,
    *,
    sandbox: Sandbox,
    state: str | None = None,
    expires_at: datetime | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if state is not None:
        values["state"] = state
    if expires_at is not None:
        values["expires_at"] = expires_at
    if payload is not None:
        values["last_opensandbox_payload"] = payload

    stmt = update(Sandbox).where(Sandbox.id == sandbox.id).values(**values)
    await session.execute(stmt)
    await session.commit()

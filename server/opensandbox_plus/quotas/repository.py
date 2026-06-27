from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.db.models import QuotaRule, Sandbox

QuotaScopeType = Literal["global", "user"]

ACTIVE_SANDBOX_STATES = ("pending", "running", "paused", "stopping", "unknown")


async def get_quota_rule(
    session: AsyncSession,
    *,
    scope_type: QuotaScopeType,
    scope_id: str,
) -> QuotaRule | None:
    stmt: Select[tuple[QuotaRule]] = select(QuotaRule).where(
        QuotaRule.scope_type == scope_type,
        QuotaRule.scope_id == scope_id,
    )
    return await session.scalar(stmt)


async def list_quota_rules(
    session: AsyncSession,
    *,
    scope_type: QuotaScopeType | None,
    scope_id: str | None,
    page: int,
    page_size: int,
) -> tuple[list[QuotaRule], int]:
    stmt: Select[tuple[QuotaRule]] = select(QuotaRule)
    count_stmt = select(func.count()).select_from(QuotaRule)
    if scope_type is not None:
        stmt = stmt.where(QuotaRule.scope_type == scope_type)
        count_stmt = count_stmt.where(QuotaRule.scope_type == scope_type)
    if scope_id is not None:
        stmt = stmt.where(QuotaRule.scope_id == scope_id)
        count_stmt = count_stmt.where(QuotaRule.scope_id == scope_id)

    stmt = (
        stmt.order_by(QuotaRule.scope_type, QuotaRule.scope_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = await session.scalars(stmt)
    total = int(await session.scalar(count_stmt) or 0)
    return list(rows), total


async def upsert_quota_rule(
    session: AsyncSession,
    *,
    quota_id: str,
    scope_type: QuotaScopeType,
    scope_id: str,
    max_running_sandboxes: int | None,
    max_timeout_seconds: int | None,
    max_create_per_minute: int | None,
    allowed_runtime_profile_ids: list[str] | None,
    allowed_image_patterns: list[str] | None,
) -> QuotaRule:
    stmt = (
        insert(QuotaRule)
        .values(
            id=quota_id,
            scope_type=scope_type,
            scope_id=scope_id,
            max_running_sandboxes=max_running_sandboxes,
            max_timeout_seconds=max_timeout_seconds,
            max_create_per_minute=max_create_per_minute,
            allowed_runtime_profile_ids=allowed_runtime_profile_ids,
            allowed_image_patterns=allowed_image_patterns,
        )
        .on_conflict_do_update(
            index_elements=[QuotaRule.id],
            set_={
                "scope_type": scope_type,
                "scope_id": scope_id,
                "max_running_sandboxes": max_running_sandboxes,
                "max_timeout_seconds": max_timeout_seconds,
                "max_create_per_minute": max_create_per_minute,
                "allowed_runtime_profile_ids": allowed_runtime_profile_ids,
                "allowed_image_patterns": allowed_image_patterns,
                "updated_at": func.now(),
            },
        )
        .returning(QuotaRule)
    )
    rule = await session.scalar(stmt)
    await session.commit()
    if rule is None:
        raise RuntimeError("failed to upsert quota rule")
    return rule


async def count_active_sandboxes(
    session: AsyncSession,
    *,
    owner_subject_id: str,
) -> int:
    stmt = (
        select(func.count())
        .select_from(Sandbox)
        .where(
            Sandbox.owner_subject_id == owner_subject_id,
            Sandbox.state.in_(ACTIVE_SANDBOX_STATES),
        )
    )
    return int(await session.scalar(stmt) or 0)


async def count_created_sandboxes_since(
    session: AsyncSession,
    *,
    owner_subject_id: str,
    since: datetime,
) -> int:
    stmt = (
        select(func.count())
        .select_from(Sandbox)
        .where(
            Sandbox.owner_subject_id == owner_subject_id,
            Sandbox.created_at >= since,
        )
    )
    return int(await session.scalar(stmt) or 0)

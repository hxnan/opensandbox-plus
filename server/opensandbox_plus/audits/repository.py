from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.db.models import AuditEvent

AuditDecision = Literal["allow", "deny", "error"]


async def create_audit_event(
    session: AsyncSession,
    *,
    request_id: str,
    actor_subject_id: str | None,
    credential_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    decision: AuditDecision,
    ip: str | None,
    user_agent: str | None,
    error_code: str | None,
    payload: dict[str, Any] | None,
) -> AuditEvent:
    event = AuditEvent(
        request_id=request_id,
        actor_subject_id=actor_subject_id,
        credential_id=credential_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        ip=ip,
        user_agent=user_agent,
        error_code=error_code,
        payload=payload,
    )
    session.add(event)
    await session.commit()
    return event


async def list_audit_events(
    session: AsyncSession,
    *,
    action: str | None,
    actor_subject_id: str | None,
    credential_id: str | None,
    resource_type: str | None,
    resource_id: str | None,
    decision: AuditDecision | None,
    page: int,
    page_size: int,
) -> tuple[list[AuditEvent], int]:
    stmt: Select[tuple[AuditEvent]] = select(AuditEvent)
    count_stmt = select(func.count()).select_from(AuditEvent)

    filters = []
    if action is not None:
        filters.append(AuditEvent.action == action)
    if actor_subject_id is not None:
        filters.append(AuditEvent.actor_subject_id == actor_subject_id)
    if credential_id is not None:
        filters.append(AuditEvent.credential_id == credential_id)
    if resource_type is not None:
        filters.append(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        filters.append(AuditEvent.resource_id == resource_id)
    if decision is not None:
        filters.append(AuditEvent.decision == decision)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    stmt = (
        stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = await session.scalars(stmt)
    total = int(await session.scalar(count_stmt) or 0)
    return list(rows), total

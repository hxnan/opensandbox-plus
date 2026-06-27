from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.audits.repository import (
    AuditDecision,
    create_audit_event,
    list_audit_events as list_audit_events_from_db,
)
from opensandbox_plus.db.models import AuditEvent


async def record_audit_event(
    session: AsyncSession,
    *,
    request: Request,
    action: str,
    resource_type: str,
    decision: AuditDecision,
    actor_subject_id: str | None = None,
    credential_id: str | None = None,
    resource_id: str | None = None,
    error_code: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    return await create_audit_event(
        session,
        request_id=request_id(request),
        actor_subject_id=actor_subject_id,
        credential_id=credential_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        error_code=error_code,
        payload=payload,
    )


async def try_record_audit_event(
    session: AsyncSession,
    *,
    request: Request,
    action: str,
    resource_type: str,
    decision: AuditDecision,
    actor_subject_id: str | None = None,
    credential_id: str | None = None,
    resource_id: str | None = None,
    error_code: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        await record_audit_event(
            session,
            request=request,
            action=action,
            resource_type=resource_type,
            decision=decision,
            actor_subject_id=actor_subject_id,
            credential_id=credential_id,
            resource_id=resource_id,
            error_code=error_code,
            payload=payload,
        )
    except Exception:
        await session.rollback()


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
    return await list_audit_events_from_db(
        session,
        action=action,
        actor_subject_id=actor_subject_id,
        credential_id=credential_id,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        page=page,
        page_size=page_size,
    )


def audit_event_to_dict(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "request_id": event.request_id,
        "actor_subject_id": event.actor_subject_id,
        "credential_id": event.credential_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "decision": event.decision,
        "ip": str(event.ip) if event.ip else None,
        "user_agent": event.user_agent,
        "error_code": event.error_code,
        "payload": event.payload,
        "created_at": event.created_at,
    }


def request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if isinstance(value, str) and value:
        return value
    header = request.headers.get("x-request-id")
    if header:
        return header[:128]
    return f"req_{uuid4().hex}"


def client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else None

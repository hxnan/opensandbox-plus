from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import require_platform_admin
from opensandbox_plus.api.management.schemas import AuditDecision, AuditEventResponse, Page
from opensandbox_plus.audits.service import audit_event_to_dict, list_audit_events
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.db.models import AuditEvent
from opensandbox_plus.db.session import get_session

router = APIRouter(prefix="/admin/audit-events")


@router.get("", response_model=Page[AuditEventResponse])
async def get_audit_events(
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    action: str | None = Query(default=None),
    actor_subject_id: str | None = Query(default=None),
    credential_id: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    decision: AuditDecision | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[AuditEventResponse]:
    events, total = await list_audit_events(
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
    return Page(
        items=[_audit_event_response(event) for event in events],
        page=page,
        page_size=page_size,
        total=total,
    )


def _audit_event_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(**audit_event_to_dict(event))

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import require_platform_admin
from opensandbox_plus.api.management.schemas import (
    Page,
    QuotaRuleRequest,
    QuotaRuleResponse,
    QuotaScopeType,
)
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.db.models import QuotaRule
from opensandbox_plus.db.session import get_session
from opensandbox_plus.quotas.service import (
    QuotaServiceError,
    list_quota_rules,
    quota_rule_to_dict,
    save_quota_rule,
)

router = APIRouter(prefix="/admin/quotas")


@router.get("", response_model=Page[QuotaRuleResponse])
async def get_quota_rules(
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    scope_type: QuotaScopeType | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[QuotaRuleResponse]:
    rules, total = await list_quota_rules(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[_quota_response(rule) for rule in rules],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.put("/{quota_id}", response_model=QuotaRuleResponse)
async def put_quota_rule(
    quota_id: str,
    payload: QuotaRuleRequest,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuotaRuleResponse:
    try:
        rule = await save_quota_rule(
            session,
            quota_id=quota_id,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            max_running_sandboxes=payload.max_running_sandboxes,
            max_timeout_seconds=payload.max_timeout_seconds,
            max_create_per_minute=payload.max_create_per_minute,
            allowed_runtime_profile_ids=payload.allowed_runtime_profile_ids,
            allowed_image_patterns=payload.allowed_image_patterns,
        )
    except QuotaServiceError as exc:
        raise _service_http_error(exc) from exc
    return _quota_response(rule)


def _quota_response(rule: QuotaRule) -> QuotaRuleResponse:
    return QuotaRuleResponse(**quota_rule_to_dict(rule))


def _service_http_error(exc: QuotaServiceError) -> HTTPException:
    detail = {"code": exc.code, "message": exc.message}
    if exc.details:
        detail["details"] = exc.details
    return HTTPException(status_code=exc.status_code, detail=detail)

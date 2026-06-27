from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import require_platform_admin
from opensandbox_plus.api.management.schemas import (
    AdminCredentialSummary,
    AdminUserSummaryResponse,
    Page,
    StatusResponse,
)
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.credentials.service import (
    CredentialServiceError,
    disable_credential_for_admin,
    list_user_credentials_for_admin,
)
from opensandbox_plus.db.models import CloudSandboxCredential
from opensandbox_plus.db.session import get_session
from opensandbox_plus.platform_status.service import (
    get_platform_status as build_platform_status,
    list_runtime_backends as build_runtime_backends,
)
from opensandbox_plus.users.service import AdminUserSummary, list_admin_users

router = APIRouter()


@router.get("/users", response_model=Page[AdminUserSummaryResponse])
async def list_users(
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[AdminUserSummaryResponse]:
    users, total = await list_admin_users(
        session,
        keyword=keyword,
        status=status,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[_user_summary_response(user) for user in users],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/users/{subject_id}/credentials", response_model=Page[AdminCredentialSummary])
async def list_user_credentials(
    subject_id: str,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[AdminCredentialSummary]:
    credentials, total = await list_user_credentials_for_admin(
        session,
        owner_subject_id=subject_id,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[_admin_credential_response(credential) for credential in credentials],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/credentials/{credential_id}:disable", response_model=StatusResponse)
async def disable_user_credential(
    credential_id: str,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse:
    try:
        credential = await disable_credential_for_admin(session, credential_id=credential_id)
    except CredentialServiceError as exc:
        raise _service_http_error(exc) from exc
    return StatusResponse(
        id=credential.id,
        status=credential.status,
        updated_at=credential.updated_at,
    )


@router.get("/runtime-backends")
async def list_runtime_backends(
    request: Request,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    return await build_runtime_backends(session, request.app.state.settings)


@router.get("/platform-status")
async def get_platform_status(
    request: Request,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    return await build_platform_status(session, request.app.state.settings)


def _user_summary_response(summary: AdminUserSummary) -> AdminUserSummaryResponse:
    user = summary.user
    return AdminUserSummaryResponse(
        subject_id=user.subject_id,
        casdoor_owner=user.casdoor_owner,
        casdoor_user=user.casdoor_user,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        roles=list(user.roles or []),
        active_credentials=summary.active_credentials,
        active_sandboxes=summary.active_sandboxes,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _admin_credential_response(credential: CloudSandboxCredential) -> AdminCredentialSummary:
    return AdminCredentialSummary(
        id=credential.id,
        owner_subject_id=credential.owner_subject_id,
        name=credential.name,
        public_prefix=credential.public_prefix,
        status=credential.status,
        expires_at=credential.expires_at,
        last_used_at=credential.last_used_at,
        last_used_ip=str(credential.last_used_ip) if credential.last_used_ip else None,
        issued_by_agent_id=credential.issued_by_agent_id,
        created_at=credential.created_at,
    )


def _service_http_error(exc: CredentialServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )

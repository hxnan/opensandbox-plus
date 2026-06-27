from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import get_current_principal
from opensandbox_plus.api.management.schemas import (
    CredentialCreateRequest,
    CredentialCreateResponse,
    CredentialSummary,
    Page,
    StatusResponse,
)
from opensandbox_plus.audits.service import try_record_audit_event
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.credentials.service import (
    CredentialServiceError,
    disable_owned_credential,
    issue_credential,
    list_owned_credentials,
    revoke_owned_credential,
    rotate_owned_credential,
)
from opensandbox_plus.db.models import CloudSandboxCredential
from opensandbox_plus.db.session import get_session

router = APIRouter(prefix="/cloud-sandbox/credentials")


@router.post("", response_model=CredentialCreateResponse)
async def create_credential(
    payload: CredentialCreateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CredentialCreateResponse:
    try:
        issued = await issue_credential(
            session,
            settings=request.app.state.settings,
            principal=principal,
            name=payload.name,
            agent_id=payload.agent_id,
            expires_in_days=payload.expires_in_days,
        )
    except CredentialServiceError as exc:
        await _audit_credential_failure(
            session,
            request=request,
            principal=principal,
            action="credential.create",
            error_code=exc.code,
            payload={"name": payload.name, "agent_id": payload.agent_id},
        )
        raise _service_http_error(exc) from exc
    await _audit_credential_success(
        session,
        request=request,
        principal=principal,
        action="credential.create",
        credential_id=issued.credential.id,
        payload={
            "name": issued.credential.name,
            "public_prefix": issued.credential.public_prefix,
            "agent_id": issued.credential.issued_by_agent_id,
        },
    )
    return _issued_response(issued.credential, issued.key)


@router.get("", response_model=Page[CredentialSummary])
async def list_credentials(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[CredentialSummary]:
    credentials, total = await list_owned_credentials(
        session,
        principal=principal,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[_summary_response(credential) for credential in credentials],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.delete("/{credential_id}", response_model=StatusResponse)
async def delete_credential(
    credential_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse:
    try:
        credential = await revoke_owned_credential(
            session,
            principal=principal,
            credential_id=credential_id,
        )
    except CredentialServiceError as exc:
        await _audit_credential_failure(
            session,
            request=request,
            principal=principal,
            action="credential.revoke",
            credential_id=credential_id,
            error_code=exc.code,
        )
        raise _service_http_error(exc) from exc
    await _audit_credential_success(
        session,
        request=request,
        principal=principal,
        action="credential.revoke",
        credential_id=credential.id,
    )
    return _status_response(credential)


@router.post("/{credential_id}:rotate", response_model=CredentialCreateResponse)
async def rotate_credential(
    credential_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CredentialCreateResponse:
    try:
        issued = await rotate_owned_credential(
            session,
            settings=request.app.state.settings,
            principal=principal,
            credential_id=credential_id,
        )
    except CredentialServiceError as exc:
        await _audit_credential_failure(
            session,
            request=request,
            principal=principal,
            action="credential.rotate",
            credential_id=credential_id,
            error_code=exc.code,
        )
        raise _service_http_error(exc) from exc
    await _audit_credential_success(
        session,
        request=request,
        principal=principal,
        action="credential.rotate",
        credential_id=issued.credential.id,
        payload={"public_prefix": issued.credential.public_prefix},
    )
    return _issued_response(issued.credential, issued.key)


@router.post("/{credential_id}:disable", response_model=StatusResponse)
async def disable_credential(
    credential_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse:
    try:
        credential = await disable_owned_credential(
            session,
            principal=principal,
            credential_id=credential_id,
        )
    except CredentialServiceError as exc:
        await _audit_credential_failure(
            session,
            request=request,
            principal=principal,
            action="credential.disable",
            credential_id=credential_id,
            error_code=exc.code,
        )
        raise _service_http_error(exc) from exc
    await _audit_credential_success(
        session,
        request=request,
        principal=principal,
        action="credential.disable",
        credential_id=credential.id,
    )
    return _status_response(credential)


def _service_http_error(exc: CredentialServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _issued_response(
    credential: CloudSandboxCredential,
    key: str,
) -> CredentialCreateResponse:
    return CredentialCreateResponse(
        id=credential.id,
        name=credential.name,
        public_prefix=credential.public_prefix,
        key=key,
        status=credential.status,
        expires_at=credential.expires_at,
        created_at=credential.created_at,
    )


def _summary_response(credential: CloudSandboxCredential) -> CredentialSummary:
    return CredentialSummary(
        id=credential.id,
        name=credential.name,
        public_prefix=credential.public_prefix,
        status=credential.status,
        expires_at=credential.expires_at,
        last_used_at=credential.last_used_at,
        last_used_ip=str(credential.last_used_ip) if credential.last_used_ip else None,
        issued_by_agent_id=credential.issued_by_agent_id,
        created_at=credential.created_at,
    )


def _status_response(credential: CloudSandboxCredential) -> StatusResponse:
    return StatusResponse(
        id=credential.id,
        status=credential.status,
        updated_at=credential.updated_at,
    )


async def _audit_credential_success(
    session: AsyncSession,
    *,
    request: Request,
    principal: Principal,
    action: str,
    credential_id: str,
    payload: dict[str, object] | None = None,
) -> None:
    await try_record_audit_event(
        session,
        request=request,
        actor_subject_id=principal.subject_id,
        action=action,
        resource_type="cloud_sandbox_credential",
        resource_id=credential_id,
        decision="allow",
        payload=payload,
    )


async def _audit_credential_failure(
    session: AsyncSession,
    *,
    request: Request,
    principal: Principal,
    action: str,
    error_code: str,
    credential_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    await try_record_audit_event(
        session,
        request=request,
        actor_subject_id=principal.subject_id,
        action=action,
        resource_type="cloud_sandbox_credential",
        resource_id=credential_id,
        decision="deny",
        error_code=error_code,
        payload=payload,
    )

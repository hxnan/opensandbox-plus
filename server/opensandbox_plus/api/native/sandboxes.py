from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import get_cloud_sandbox_principal
from opensandbox_plus.adapter.client import OpenSandboxClient, opensandbox_payload
from opensandbox_plus.adapter.proxy import proxy_http_to_opensandbox
from opensandbox_plus.audits.service import try_record_audit_event
from opensandbox_plus.auth.principal import CloudSandboxPrincipal
from opensandbox_plus.db.session import get_session
from opensandbox_plus.quotas.service import QuotaServiceError, enforce_sandbox_create_quota
from opensandbox_plus.sandboxes.service import (
    ensure_owned_sandbox,
    extract_sandbox_id,
    filter_list_payload_to_owner,
    record_created_sandbox,
    record_deleted_sandbox,
    record_sandbox_payload,
    record_sandbox_state,
)

router = APIRouter()


@router.api_route("/v1/sandboxes", methods=["POST", "GET"])
@router.api_route("/sandboxes", methods=["POST", "GET"])
async def sandboxes_root(
    request: Request,
    principal: CloudSandboxPrincipal = Depends(get_cloud_sandbox_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    client = OpenSandboxClient(request.app.state.settings)
    if request.method == "POST":
        request_payload = await _json_body(request)
        try:
            request_payload = await enforce_sandbox_create_quota(
                session,
                principal=principal,
                request_payload=request_payload,
            )
        except QuotaServiceError as exc:
            await _audit_sandbox_operation(
                session,
                request=request,
                principal=principal,
                action="sandbox.create",
                resource_id=None,
                decision="deny",
                error_code=exc.code,
                payload=exc.details,
            )
            raise _quota_http_error(exc) from exc
        try:
            response = await client.request(
                request.method,
                _backend_path(request),
                query_params=dict(request.query_params),
                body=_json_body_bytes(request_payload),
                content_type="application/json",
            )
        except httpx.HTTPError as exc:
            await _audit_sandbox_operation(
                session,
                request=request,
                principal=principal,
                action="sandbox.create",
                resource_id=None,
                decision="error",
                error_code="OPENSANDBOX_BACKEND_ERROR",
                payload={"message": str(exc)},
            )
            raise _opensandbox_backend_error(exc) from exc
        payload = opensandbox_payload(response)
        if 200 <= response.status_code < 300:
            try:
                await record_created_sandbox(
                    session,
                    settings=request.app.state.settings,
                    principal=principal,
                    request_payload=request_payload,
                    response_payload=payload,
                )
            except HTTPException as exc:
                await _audit_sandbox_operation(
                    session,
                    request=request,
                    principal=principal,
                    action="sandbox.create",
                    resource_id=extract_sandbox_id(payload),
                    decision=_http_exception_decision(exc),
                    error_code=_http_exception_code(exc),
                    payload={"backend_status_code": response.status_code},
                )
                raise
            await _audit_sandbox_operation(
                session,
                request=request,
                principal=principal,
                action="sandbox.create",
                resource_id=extract_sandbox_id(payload),
                backend_status_code=response.status_code,
                payload={
                    "image": _payload_image(request_payload),
                    "timeout": request_payload.get("timeout"),
                },
            )
        else:
            await _audit_sandbox_operation(
                session,
                request=request,
                principal=principal,
                action="sandbox.create",
                resource_id=extract_sandbox_id(payload),
                backend_status_code=response.status_code,
                error_code=_backend_error_code(payload, response.status_code),
            )
        return _backend_response(response, payload)

    response = await client.request(
        request.method,
        _backend_path(request),
        query_params=dict(request.query_params),
    )
    payload = opensandbox_payload(response)
    if 200 <= response.status_code < 300:
        payload = await filter_list_payload_to_owner(
            session,
            principal=principal,
            payload=payload,
        )
    return _backend_response(response, payload)


@router.api_route("/v1/sandboxes/{sandbox_id}", methods=["GET", "DELETE"])
@router.api_route("/sandboxes/{sandbox_id}", methods=["GET", "DELETE"])
async def sandbox_by_id(
    request: Request,
    sandbox_id: str,
    principal: CloudSandboxPrincipal = Depends(get_cloud_sandbox_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    action = "sandbox.delete" if request.method == "DELETE" else "sandbox.get"
    try:
        sandbox = await ensure_owned_sandbox(session, principal=principal, sandbox_id=sandbox_id)
    except HTTPException as exc:
        await _audit_sandbox_operation(
            session,
            request=request,
            principal=principal,
            action=action,
            resource_id=sandbox_id,
            decision=_http_exception_decision(exc),
            error_code=_http_exception_code(exc),
        )
        raise
    client = OpenSandboxClient(request.app.state.settings)
    try:
        response = await client.request(
            request.method,
            _backend_path(request, sandbox.opensandbox_id),
            query_params=dict(request.query_params),
        )
    except httpx.HTTPError as exc:
        await _audit_sandbox_operation(
            session,
            request=request,
            principal=principal,
            action=action,
            resource_id=sandbox_id,
            decision="error",
            error_code="OPENSANDBOX_BACKEND_ERROR",
            payload={"message": str(exc)},
        )
        raise _opensandbox_backend_error(exc) from exc
    payload = opensandbox_payload(response)
    if request.method == "DELETE" and 200 <= response.status_code < 300:
        await record_deleted_sandbox(session, sandbox=sandbox, payload=payload)
    if request.method == "DELETE" or response.status_code >= 400:
        await _audit_sandbox_operation(
            session,
            request=request,
            principal=principal,
            action=action,
            resource_id=sandbox_id,
            backend_status_code=response.status_code,
            error_code=None
            if 200 <= response.status_code < 300
            else _backend_error_code(payload, response.status_code),
        )
    return _backend_response(response, payload)


@router.patch("/v1/sandboxes/{sandbox_id}/metadata")
async def patch_sandbox_metadata(
    request: Request,
    sandbox_id: str,
    principal: CloudSandboxPrincipal = Depends(get_cloud_sandbox_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    sandbox = await ensure_owned_sandbox(session, principal=principal, sandbox_id=sandbox_id)
    response, payload = await _forward_owned_sandbox_request(
        request,
        sandbox.opensandbox_id,
        include_body=True,
    )
    if 200 <= response.status_code < 300 and payload:
        await record_sandbox_payload(session, sandbox=sandbox, payload=payload)
    await _audit_sandbox_operation(
        session,
        request=request,
        principal=principal,
        action="sandbox.metadata.patch",
        resource_id=sandbox_id,
        backend_status_code=response.status_code,
        error_code=None
        if 200 <= response.status_code < 300
        else _backend_error_code(payload, response.status_code),
    )
    return _backend_response(response, payload)


@router.post("/v1/sandboxes/{sandbox_id}/pause")
async def pause_sandbox(
    request: Request,
    sandbox_id: str,
    principal: CloudSandboxPrincipal = Depends(get_cloud_sandbox_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    sandbox = await ensure_owned_sandbox(session, principal=principal, sandbox_id=sandbox_id)
    response, payload = await _forward_owned_sandbox_request(request, sandbox.opensandbox_id)
    if 200 <= response.status_code < 300:
        await record_sandbox_state(session, sandbox=sandbox, state="paused")
    await _audit_sandbox_operation(
        session,
        request=request,
        principal=principal,
        action="sandbox.pause",
        resource_id=sandbox_id,
        backend_status_code=response.status_code,
        error_code=None
        if 200 <= response.status_code < 300
        else _backend_error_code(payload, response.status_code),
    )
    return _backend_response(response, payload)


@router.post("/v1/sandboxes/{sandbox_id}/resume")
async def resume_sandbox(
    request: Request,
    sandbox_id: str,
    principal: CloudSandboxPrincipal = Depends(get_cloud_sandbox_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    sandbox = await ensure_owned_sandbox(session, principal=principal, sandbox_id=sandbox_id)
    response, payload = await _forward_owned_sandbox_request(request, sandbox.opensandbox_id)
    if 200 <= response.status_code < 300:
        await record_sandbox_state(session, sandbox=sandbox, state="running")
    await _audit_sandbox_operation(
        session,
        request=request,
        principal=principal,
        action="sandbox.resume",
        resource_id=sandbox_id,
        backend_status_code=response.status_code,
        error_code=None
        if 200 <= response.status_code < 300
        else _backend_error_code(payload, response.status_code),
    )
    return _backend_response(response, payload)


@router.post("/v1/sandboxes/{sandbox_id}/renew-expiration")
async def renew_sandbox(
    request: Request,
    sandbox_id: str,
    principal: CloudSandboxPrincipal = Depends(get_cloud_sandbox_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    sandbox = await ensure_owned_sandbox(session, principal=principal, sandbox_id=sandbox_id)
    response, payload = await _forward_owned_sandbox_request(
        request,
        sandbox.opensandbox_id,
        include_body=True,
    )
    if 200 <= response.status_code < 300 and payload:
        await record_sandbox_payload(session, sandbox=sandbox, payload=payload)
    await _audit_sandbox_operation(
        session,
        request=request,
        principal=principal,
        action="sandbox.renew_expiration",
        resource_id=sandbox_id,
        backend_status_code=response.status_code,
        error_code=None
        if 200 <= response.status_code < 300
        else _backend_error_code(payload, response.status_code),
    )
    return _backend_response(response, payload)


@router.get("/v1/sandboxes/{sandbox_id}/endpoints/{port}")
async def get_endpoint(
    request: Request,
    sandbox_id: str,
    port: int,
    principal: CloudSandboxPrincipal = Depends(get_cloud_sandbox_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    sandbox = await ensure_owned_sandbox(session, principal=principal, sandbox_id=sandbox_id)
    response, payload = await _forward_owned_sandbox_request(request, sandbox.opensandbox_id)
    await _audit_sandbox_operation(
        session,
        request=request,
        principal=principal,
        action="sandbox.endpoint.get",
        resource_id=sandbox_id,
        backend_status_code=response.status_code,
        error_code=None
        if 200 <= response.status_code < 300
        else _backend_error_code(payload, response.status_code),
        payload={"port": port},
    )
    return _backend_response(response, payload)


@router.api_route(
    "/v1/sandboxes/{sandbox_id}/proxy/{port}/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@router.api_route(
    "/v1/sandboxes/{sandbox_id}/proxy/{port}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@router.api_route(
    "/sandboxes/{sandbox_id}/proxy/{port}/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@router.api_route(
    "/sandboxes/{sandbox_id}/proxy/{port}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_sandbox(
    request: Request,
    sandbox_id: str,
    port: int,
    full_path: str = "",
    principal: CloudSandboxPrincipal = Depends(get_cloud_sandbox_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    sandbox = await ensure_owned_sandbox(session, principal=principal, sandbox_id=sandbox_id)
    return await proxy_http_to_opensandbox(
        request,
        settings=request.app.state.settings,
        backend_path=_backend_path(request, sandbox.opensandbox_id),
    )


async def _forward_owned_sandbox_request(
    request: Request,
    opensandbox_id: str,
    *,
    include_body: bool = False,
):
    client = OpenSandboxClient(request.app.state.settings)
    return await _send_backend_request(request, client, _backend_path(request, opensandbox_id), include_body)


async def _send_backend_request(
    request: Request,
    client: OpenSandboxClient,
    path: str,
    include_body: bool,
):
    response = await client.request(
        request.method,
        path,
        query_params=dict(request.query_params),
        body=await request.body() if include_body else None,
        content_type=request.headers.get("content-type") if include_body else None,
    )
    return response, opensandbox_payload(response)


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "request body must be a JSON object"},
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "request body must be a JSON object"},
        )
    return body


def _json_body_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _backend_path(request: Request, sandbox_id: str | None = None) -> str:
    path = request.url.path
    if sandbox_id is None:
        return path
    parts = path.split("/")
    try:
        index = parts.index("sandboxes") + 1
        parts[index] = sandbox_id
    except (ValueError, IndexError):
        return path
    return "/".join(parts)


def _quota_http_error(exc: QuotaServiceError) -> HTTPException:
    detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.details:
        detail["details"] = exc.details
    return HTTPException(status_code=exc.status_code, detail=detail)


def _opensandbox_backend_error(exc: httpx.HTTPError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"code": "OPENSANDBOX_BACKEND_ERROR", "message": str(exc)},
    )


async def _audit_sandbox_operation(
    session: AsyncSession,
    *,
    request: Request,
    principal: CloudSandboxPrincipal,
    action: str,
    resource_id: str | None,
    decision: str | None = None,
    backend_status_code: int | None = None,
    error_code: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    audit_payload = dict(payload or {})
    if backend_status_code is not None:
        audit_payload["backend_status_code"] = backend_status_code
    await try_record_audit_event(
        session,
        request=request,
        actor_subject_id=principal.subject_id,
        credential_id=principal.credential_id,
        action=action,
        resource_type="sandbox",
        resource_id=resource_id,
        decision=decision or _decision_from_status(backend_status_code),
        error_code=error_code,
        payload=audit_payload or None,
    )


def _decision_from_status(status_code: int | None) -> str:
    if status_code is not None and 200 <= status_code < 300:
        return "allow"
    if status_code is not None and status_code < 500:
        return "deny"
    return "error"


def _backend_error_code(payload: dict[str, Any], status_code: int) -> str:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        code = detail.get("code")
        if isinstance(code, str) and code:
            return code
    code = payload.get("code")
    if isinstance(code, str) and code:
        return code
    if status_code >= 500:
        return "OPENSANDBOX_BACKEND_ERROR"
    return "OPENSANDBOX_REQUEST_FAILED"


def _http_exception_code(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        if isinstance(code, str) and code:
            return code
    if exc.status_code >= 500:
        return "INTERNAL_ERROR"
    return "REQUEST_DENIED"


def _http_exception_decision(exc: HTTPException) -> str:
    return "error" if exc.status_code >= 500 else "deny"


def _payload_image(payload: dict[str, Any]) -> str | None:
    image = payload.get("image")
    if isinstance(image, str):
        return image
    if isinstance(image, dict):
        uri = image.get("uri")
        return uri if isinstance(uri, str) else None
    return None


def _backend_response(response, payload: dict[str, Any]) -> Response:
    content_type = response.headers.get("content-type", "")
    if payload and "application/json" in content_type:
        return JSONResponse(content=payload, status_code=response.status_code)
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=content_type or None,
    )

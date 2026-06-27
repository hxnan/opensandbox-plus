from __future__ import annotations

import time
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

logger = structlog.get_logger("opensandbox_plus.access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _request_id_from_header(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            _log_request(request, request_id, time.perf_counter() - started_at, None, True)
            raise
        response.headers[REQUEST_ID_HEADER] = request_id
        _log_request(request, request_id, time.perf_counter() - started_at, response.status_code, False)
        return response


def _request_id_from_header(value: str | None) -> str:
    if value:
        normalized = value.strip()
        if normalized and len(normalized) <= 128:
            return normalized
    return f"req_{uuid4().hex}"


def _log_request(
    request: Request,
    request_id: str,
    duration_seconds: float,
    status_code: int | None,
    unhandled_error: bool,
) -> None:
    principal = getattr(request.state, "current_principal", None)
    cloud_principal = getattr(request.state, "cloud_sandbox_principal", None)
    if cloud_principal is not None:
        principal = cloud_principal.principal
    logger.info(
        "http.request.completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=status_code,
        duration_ms=round(duration_seconds * 1000, 2),
        user_id=getattr(principal, "subject_id", None),
        credential_id=getattr(cloud_principal, "credential_id", None),
        client_ip=request.client.host if request.client else None,
        unhandled_error=unhandled_error,
    )

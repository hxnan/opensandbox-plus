from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _request_id_from_header(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _request_id_from_header(value: str | None) -> str:
    if value:
        normalized = value.strip()
        if normalized and len(normalized) <= 128:
            return normalized
    return f"req_{uuid4().hex}"

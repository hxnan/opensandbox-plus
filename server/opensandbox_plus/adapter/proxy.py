from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

import httpx
from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse

from opensandbox_plus.auth.constants import SANDBOX_API_KEY_HEADER
from opensandbox_plus.config import Settings

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    SANDBOX_API_KEY_HEADER.lower(),
}


async def proxy_http_to_opensandbox(
    request: Request,
    *,
    settings: Settings,
    backend_path: str,
) -> StreamingResponse:
    if request.headers.get("upgrade", "").lower() == "websocket":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"code": "NOT_IMPLEMENTED", "message": "WebSocket proxy is not implemented yet"},
        )

    client = httpx.AsyncClient(timeout=None)
    headers = _filter_request_headers(
        request.headers,
        connection_header=request.headers.get("connection"),
    )
    headers[SANDBOX_API_KEY_HEADER] = settings.opensandbox_internal_api_key
    _inject_forwarded_headers(headers, request)

    target_url = settings.opensandbox_default_backend_base_url.rstrip("/") + backend_path
    try:
        outbound = client.build_request(
            method=request.method,
            url=target_url,
            params=request.url.query if request.url.query else None,
            headers=headers,
            content=request.stream(),
        )
        backend_response = await client.send(outbound, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "OPENSANDBOX_BACKEND_ERROR", "message": str(exc)},
        ) from exc

    return StreamingResponse(
        _stream_and_close(backend_response, client),
        status_code=backend_response.status_code,
        headers=_filter_response_headers(backend_response.headers),
    )


async def _stream_and_close(
    response: httpx.Response,
    client: httpx.AsyncClient,
) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    finally:
        await response.aclose()
        await client.aclose()


def _filter_request_headers(
    headers: Mapping[str, str],
    *,
    connection_header: str | None,
) -> dict[str, str]:
    excluded = set(HOP_BY_HOP_HEADERS) | set(SENSITIVE_HEADERS)
    if connection_header:
        excluded.update(
            value.strip().lower() for value in connection_header.split(",") if value.strip()
        )

    forwarded: dict[str, str] = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower != "host" and key_lower not in excluded:
            forwarded[key] = value
    return forwarded


def _inject_forwarded_headers(headers: dict[str, str], request: Request) -> None:
    existing = {key.lower() for key in headers}
    if "x-forwarded-proto" not in existing:
        headers["X-Forwarded-Proto"] = request.url.scheme
    inbound_host = request.headers.get("host", "")
    if inbound_host and "x-forwarded-host" not in existing:
        headers["X-Forwarded-Host"] = inbound_host
    if request.client and "x-forwarded-for" not in existing:
        headers["X-Forwarded-For"] = request.client.host


def _filter_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    excluded = set(HOP_BY_HOP_HEADERS)
    connection_header = headers.get("connection")
    if connection_header:
        excluded.update(
            value.strip().lower() for value in connection_header.split(",") if value.strip()
        )
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in excluded
    }

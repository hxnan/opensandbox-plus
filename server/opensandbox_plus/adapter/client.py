from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from opensandbox_plus.auth.constants import SANDBOX_API_KEY_HEADER
from opensandbox_plus.api.middleware import REQUEST_ID_HEADER
from opensandbox_plus.config import Settings


class OpenSandboxClient:
    def __init__(self, settings: Settings, *, request_id: str | None = None) -> None:
        self._base_url = settings.opensandbox_default_backend_base_url.rstrip("/")
        self._api_key = settings.opensandbox_internal_api_key
        self._request_id = request_id

    async def request(
        self,
        method: str,
        path: str,
        *,
        query_params: Mapping[str, str] | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        headers = {SANDBOX_API_KEY_HEADER: self._api_key}
        if self._request_id:
            headers[REQUEST_ID_HEADER] = self._request_id
        if content_type:
            headers["content-type"] = content_type

        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            return await client.request(
                method,
                f"{self._base_url}{path}",
                params=query_params,
                content=body,
                headers=headers,
            )


def opensandbox_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}

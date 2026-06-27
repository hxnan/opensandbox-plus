from __future__ import annotations

import httpx
import pytest

from opensandbox_plus.adapter.client import OpenSandboxClient
from opensandbox_plus.auth.constants import SANDBOX_API_KEY_HEADER
from opensandbox_plus.config import Settings


@pytest.mark.asyncio
async def test_opensandbox_client_forwards_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_request: httpx.Request | None = None

    async def fake_send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    client = OpenSandboxClient(
        Settings(
            opensandbox_default_backend_base_url="http://opensandbox.test",
            opensandbox_internal_api_key="internal-key",
            background_jobs_enabled=False,
        ),
        request_id="req-downstream",
    )

    response = await client.request("POST", "/v1/sandboxes", body=b"{}", content_type="application/json")

    assert response.status_code == 200
    assert captured_request is not None
    assert str(captured_request.url) == "http://opensandbox.test/v1/sandboxes"
    assert captured_request.headers[SANDBOX_API_KEY_HEADER] == "internal-key"
    assert captured_request.headers["X-Request-ID"] == "req-downstream"
    assert captured_request.headers["content-type"] == "application/json"

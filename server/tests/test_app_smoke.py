import httpx
import pytest

from opensandbox_plus.config import Settings
from opensandbox_plus.main import create_app


@pytest.mark.asyncio
async def test_health_endpoint_and_request_id_header() -> None:
    app = create_app(Settings(background_jobs_enabled=False))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "opensandbox-plus",
        "app_role": "all",
    }
    assert response.headers["X-Request-ID"] == "req-test"


@pytest.mark.asyncio
async def test_health_endpoint_generates_request_id() -> None:
    app = create_app(Settings(background_jobs_enabled=False))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")

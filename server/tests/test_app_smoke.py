import httpx
import pytest

from opensandbox_plus.api import middleware
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


@pytest.mark.asyncio
async def test_request_logging_includes_trace_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    logged_events = []

    class CaptureLogger:
        def info(self, event: str, **kwargs) -> None:
            logged_events.append((event, kwargs))

    monkeypatch.setattr(middleware, "logger", CaptureLogger())
    app = create_app(Settings(background_jobs_enabled=False))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health", headers={"X-Request-ID": "req-log-test"})

    assert response.status_code == 200
    assert logged_events
    event, fields = logged_events[-1]
    assert event == "http.request.completed"
    assert fields["request_id"] == "req-log-test"
    assert fields["method"] == "GET"
    assert fields["path"] == "/health"
    assert fields["status_code"] == 200
    assert fields["unhandled_error"] is False
    assert isinstance(fields["duration_ms"], float)


@pytest.mark.asyncio
async def test_casdoor_static_assets_are_served_locally() -> None:
    app = create_app(Settings(background_jobs_enabled=False))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        logo_response = await client.get("/casdoor-static/logo.svg")
        flag_response = await client.get("/casdoor-static/flag-icons/CN.svg")
        manifest_response = await client.get("/casdoor-static/site/casdoor/manifest.json")

    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"].startswith("image/svg+xml")
    assert "OpenSandbox Plus logo" in logo_response.text
    assert flag_response.status_code == 200
    assert flag_response.headers["content-type"].startswith("image/svg+xml")
    assert manifest_response.status_code == 200
    assert manifest_response.json()["name"] == "OpenSandbox Plus Console"


@pytest.mark.asyncio
async def test_error_response_includes_code_and_request_id() -> None:
    app = create_app(Settings(background_jobs_enabled=False))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/me", headers={"X-Request-ID": "req-error-test"})

    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "req-error-test"
    assert response.json() == {
        "detail": {
            "code": "UNAUTHENTICATED",
            "message": "missing Authorization header",
            "request_id": "req-error-test",
        }
    }


@pytest.mark.asyncio
async def test_openapi_exports_common_error_schema() -> None:
    app = create_app(Settings(background_jobs_enabled=False))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert (
        schema["paths"]["/api/v1/me"]["get"]["responses"]["401"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        == "#/components/schemas/ErrorResponse"
    )

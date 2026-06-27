from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Header, HTTPException

from opensandbox_plus.api import dependencies
from opensandbox_plus.api.management import audit as audit_routes
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.config import Settings
from opensandbox_plus.db import session as db_session
from opensandbox_plus.main import create_app


class DummySession:
    async def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_admin_can_get_audit_event_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)
    admin = _admin()

    async def fake_session():
        yield DummySession()

    async def fake_current_principal(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> Principal:
        if authorization == "Bearer admin-token":
            return admin
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED"})

    async def fake_get_audit_event(session, *, event_id: int):
        assert event_id == 42
        return SimpleNamespace(
            id=42,
            request_id="req-audit-detail",
            actor_subject_id=admin.subject_id,
            credential_id="cred_agent",
            action="credential.disable",
            resource_type="cloud_sandbox_credential",
            resource_id="cred_agent",
            decision="allow",
            ip="127.0.0.1",
            user_agent="pytest",
            error_code=None,
            payload={"reason": "admin_disable"},
            created_at=now,
        )

    monkeypatch.setattr(audit_routes, "get_audit_event", fake_get_audit_event)

    app = create_app(Settings(background_jobs_enabled=False))
    app.dependency_overrides[db_session.get_session] = fake_session
    app.dependency_overrides[dependencies.get_current_principal] = fake_current_principal

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/admin/audit-events/42",
            headers={"Authorization": "Bearer admin-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": 42,
        "request_id": "req-audit-detail",
        "actor_subject_id": admin.subject_id,
        "credential_id": "cred_agent",
        "action": "credential.disable",
        "resource_type": "cloud_sandbox_credential",
        "resource_id": "cred_agent",
        "decision": "allow",
        "ip": "127.0.0.1",
        "user_agent": "pytest",
        "error_code": None,
        "payload": {"reason": "admin_disable"},
        "created_at": "2026-06-27T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_audit_event_detail_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = _admin()

    async def fake_session():
        yield DummySession()

    async def fake_current_principal(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> Principal:
        if authorization == "Bearer admin-token":
            return admin
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED"})

    async def fake_get_audit_event(session, *, event_id: int):
        assert event_id == 404
        return None

    monkeypatch.setattr(audit_routes, "get_audit_event", fake_get_audit_event)

    app = create_app(Settings(background_jobs_enabled=False))
    app.dependency_overrides[db_session.get_session] = fake_session
    app.dependency_overrides[dependencies.get_current_principal] = fake_current_principal

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/admin/audit-events/404",
            headers={"Authorization": "Bearer admin-token", "X-Request-ID": "req-missing-audit"},
        )

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "NOT_FOUND",
            "message": "audit event not found",
            "request_id": "req-missing-audit",
        }
    }


def _admin() -> Principal:
    return Principal(
        subject_id="casdoor:built-in:admin",
        casdoor_owner="built-in",
        casdoor_user="admin",
        username="admin",
        email="admin@example.com",
        display_name="Admin",
        roles=["osb_platform_admin"],
        status="active",
    )

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import Header, HTTPException

from opensandbox_plus.api import dependencies
from opensandbox_plus.api.management import admin as admin_routes
from opensandbox_plus.api.management import credentials as credential_routes
from opensandbox_plus.api.native import sandboxes as sandbox_routes
from opensandbox_plus.auth.principal import CloudSandboxPrincipal, Principal
from opensandbox_plus.config import Settings
from opensandbox_plus.credentials.service import IssuedCredential
from opensandbox_plus.db import session as db_session
from opensandbox_plus.main import create_app


class DummySession:
    async def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_agent_key_sandbox_flow_and_admin_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    agent = Principal(
        subject_id="casdoor:built-in:alice",
        casdoor_owner="built-in",
        casdoor_user="alice",
        username="alice",
        email="alice@example.com",
        display_name="Alice",
        roles=["osb_agent_user"],
        status="active",
    )
    admin = Principal(
        subject_id="casdoor:built-in:admin",
        casdoor_owner="built-in",
        casdoor_user="admin",
        username="admin",
        email="admin@example.com",
        display_name="Admin",
        roles=["osb_platform_admin"],
        status="active",
    )
    issued_key = "osb_u_test123." + ("s" * 32)
    credentials: dict[str, SimpleNamespace] = {}
    sandboxes_by_owner: defaultdict[str, set[str]] = defaultdict(set)
    backend_requests: list[dict[str, Any]] = []

    async def fake_session():
        yield DummySession()

    async def fake_current_principal(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> Principal:
        if authorization == "Bearer agent-token":
            return agent
        if authorization == "Bearer admin-token":
            return admin
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED"})

    async def fake_cloud_principal(
        api_key: str | None = Header(default=None, alias="OPEN-SANDBOX-API-KEY"),
    ) -> CloudSandboxPrincipal:
        credential = credentials.get("cred_agent")
        if api_key != issued_key or credential is None or credential.status != "active":
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_CLOUD_SANDBOX_CREDENTIAL"},
            )
        return CloudSandboxPrincipal(
            principal=agent,
            credential_id=credential.id,
            public_prefix=credential.public_prefix,
        )

    async def fake_issue_credential(
        session,
        *,
        settings,
        principal: Principal,
        name: str,
        agent_id: str | None,
        expires_in_days: int | None,
    ) -> IssuedCredential:
        assert principal == agent
        credential = SimpleNamespace(
            id="cred_agent",
            owner_subject_id=agent.subject_id,
            name=name,
            public_prefix="test123",
            status="active",
            expires_at=now + timedelta(days=expires_in_days or 1),
            last_used_at=None,
            last_used_ip=None,
            issued_by_agent_id=agent_id,
            created_at=now,
            updated_at=now,
        )
        credentials[credential.id] = credential
        return IssuedCredential(credential=credential, key=issued_key)

    async def fake_list_owned_credentials(session, *, principal: Principal, page: int, page_size: int):
        owned = [
            credential
            for credential in credentials.values()
            if credential.owner_subject_id == principal.subject_id
        ]
        return owned[(page - 1) * page_size : page * page_size], len(owned)

    async def fake_list_admin_users(session, *, keyword, status, page: int, page_size: int):
        user = SimpleNamespace(
            subject_id=agent.subject_id,
            casdoor_owner=agent.casdoor_owner,
            casdoor_user=agent.casdoor_user,
            username=agent.username,
            email=agent.email,
            display_name=agent.display_name,
            status=agent.status,
            roles=agent.roles,
            created_at=now,
            updated_at=now,
        )
        summary = admin_routes.AdminUserSummary(
            user=user,
            active_credentials=sum(
                1
                for credential in credentials.values()
                if credential.owner_subject_id == agent.subject_id
                and credential.status == "active"
            ),
            active_sandboxes=len(sandboxes_by_owner[agent.subject_id]),
        )
        return [summary][(page - 1) * page_size : page * page_size], 1

    async def fake_list_user_credentials_for_admin(
        session,
        *,
        owner_subject_id: str,
        page: int,
        page_size: int,
    ):
        owned = [
            credential
            for credential in credentials.values()
            if credential.owner_subject_id == owner_subject_id
        ]
        return owned[(page - 1) * page_size : page * page_size], len(owned)

    async def fake_disable_credential_for_admin(session, *, credential_id: str):
        credential = credentials[credential_id]
        credential.status = "disabled"
        credential.updated_at = now + timedelta(minutes=1)
        return credential

    async def fake_backend_request(
        self,
        method: str,
        path: str,
        *,
        query_params=None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        backend_requests.append(
            {
                "method": method,
                "path": path,
                "api_key": self._api_key,
                "content_type": content_type,
            }
        )
        if method == "POST" and path == "/v1/sandboxes":
            payload = json.loads((body or b"{}").decode("utf-8"))
            assert payload["image"] == "python:3.12-slim"
            return httpx.Response(
                201,
                json={
                    "id": "sbx_agent",
                    "state": "running",
                    "image": {"uri": payload["image"]},
                    "expiresAt": "2026-01-01T01:00:00Z",
                },
            )
        if method == "GET" and path == "/v1/sandboxes":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "sbx_agent", "state": "running"},
                        {"id": "sbx_other", "state": "running"},
                    ],
                    "total": 2,
                },
            )
        raise AssertionError(f"unexpected backend call: {method} {path}")

    async def fake_enforce_quota(session, *, principal, request_payload):
        return request_payload

    async def fake_record_created_sandbox(
        session,
        *,
        settings,
        principal: CloudSandboxPrincipal,
        request_payload,
        response_payload,
    ) -> None:
        sandboxes_by_owner[principal.subject_id].add(response_payload["id"])

    async def fake_filter_list_payload_to_owner(session, *, principal, payload):
        owned = sandboxes_by_owner[principal.subject_id]
        items = [item for item in payload["items"] if item["id"] in owned]
        return {**payload, "items": items, "total": len(items)}

    async def fake_audit(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(credential_routes, "issue_credential", fake_issue_credential)
    monkeypatch.setattr(credential_routes, "list_owned_credentials", fake_list_owned_credentials)
    monkeypatch.setattr(credential_routes, "try_record_audit_event", fake_audit)
    monkeypatch.setattr(admin_routes, "list_admin_users", fake_list_admin_users)
    monkeypatch.setattr(
        admin_routes,
        "list_user_credentials_for_admin",
        fake_list_user_credentials_for_admin,
    )
    monkeypatch.setattr(
        admin_routes,
        "disable_credential_for_admin",
        fake_disable_credential_for_admin,
    )
    monkeypatch.setattr(sandbox_routes.OpenSandboxClient, "request", fake_backend_request)
    monkeypatch.setattr(sandbox_routes, "enforce_sandbox_create_quota", fake_enforce_quota)
    monkeypatch.setattr(sandbox_routes, "record_created_sandbox", fake_record_created_sandbox)
    monkeypatch.setattr(
        sandbox_routes,
        "filter_list_payload_to_owner",
        fake_filter_list_payload_to_owner,
    )
    monkeypatch.setattr(sandbox_routes, "try_record_audit_event", fake_audit)

    app = create_app(
        Settings(
            background_jobs_enabled=False,
            opensandbox_internal_api_key="internal-test-key",
        )
    )
    app.dependency_overrides[db_session.get_session] = fake_session
    app.dependency_overrides[dependencies.get_current_principal] = fake_current_principal
    app.dependency_overrides[dependencies.get_cloud_sandbox_principal] = fake_cloud_principal

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        issued = await client.post(
            "/api/v1/cloud-sandbox/credentials",
            headers={"Authorization": "Bearer agent-token"},
            json={"name": "local-agent", "agent_id": "agent-1", "expires_in_days": 1},
        )
        assert issued.status_code == 200
        assert issued.json()["key"] == issued_key

        created = await client.post(
            "/v1/sandboxes",
            headers={"OPEN-SANDBOX-API-KEY": issued_key},
            json={"image": "python:3.12-slim", "timeout": 60},
        )
        assert created.status_code == 201
        assert created.json()["id"] == "sbx_agent"

        listed = await client.get(
            "/v1/sandboxes",
            headers={"OPEN-SANDBOX-API-KEY": issued_key},
        )
        assert listed.status_code == 200
        assert listed.json() == {"items": [{"id": "sbx_agent", "state": "running"}], "total": 1}

        users = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert users.status_code == 200
        assert users.json()["items"][0]["active_credentials"] == 1
        assert users.json()["items"][0]["active_sandboxes"] == 1

        admin_credentials = await client.get(
            f"/api/v1/admin/users/{agent.subject_id}/credentials",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert admin_credentials.status_code == 200
        assert admin_credentials.json()["items"][0]["status"] == "active"

        disabled = await client.post(
            "/api/v1/admin/credentials/cred_agent:disable",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "disabled"

        denied = await client.post(
            "/v1/sandboxes",
            headers={"OPEN-SANDBOX-API-KEY": issued_key},
            json={"image": "python:3.12-slim"},
        )
        assert denied.status_code == 401

    assert all(request["api_key"] == "internal-test-key" for request in backend_requests)

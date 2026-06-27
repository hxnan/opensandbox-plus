from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Header, HTTPException

from opensandbox_plus.api import dependencies
from opensandbox_plus.api.management import clusters as cluster_routes
from opensandbox_plus.api.management import images as image_routes
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.config import Settings
from opensandbox_plus.db import session as db_session
from opensandbox_plus.main import create_app


class DummySession:
    async def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_next_stage_admin_cluster_image_and_ack_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)
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

    async def fake_session():
        yield DummySession()

    async def fake_current_principal(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> Principal:
        if authorization == "Bearer admin-token":
            return admin
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED"})

    async def fake_save_cluster(session, **kwargs):
        assert kwargs["provider"] == "aliyun_ack"
        assert kwargs["external_cluster_id"] == "ack-prod-1"
        return _cluster(now, **kwargs)

    async def fake_list_clusters(session, **kwargs):
        return [_cluster(now, cluster_id="cluster_ack", name="ack-prod")], 1

    async def fake_save_ack_deployment(session, **kwargs):
        assert kwargs["aliyun_cluster_id"] == "ack-prod-1"
        return SimpleNamespace(
            id="ackdep_1",
            runtime_backend_id=kwargs["runtime_backend_id"],
            aliyun_cluster_id=kwargs["aliyun_cluster_id"],
            region=kwargs["region"],
            namespace=kwargs["namespace"],
            vpc_id=kwargs["vpc_id"],
            registry_url=kwargs["registry_url"],
            kubeconfig_secret_ref=kwargs["kubeconfig_secret_ref"],
            status="draft",
            precheck_payload=kwargs["precheck_payload"],
            deployment_payload=kwargs["deployment_payload"],
            last_error=None,
            created_at=now,
            updated_at=now,
        )

    async def fake_save_image(session, **kwargs):
        assert kwargs["created_by_subject_id"] == admin.subject_id
        return _image(now, **kwargs)

    async def fake_create_distribution_plan(session, *, image_id: str):
        assert image_id == "img_test" or image_id.startswith("img_")
        return [
            SimpleNamespace(
                id="dist_1",
                image_id=image_id,
                runtime_backend_id="cluster_ack",
                registry_url="registry.cn-hangzhou.aliyuncs.com/osb",
                target_ref="registry.cn-hangzhou.aliyuncs.com/osb/python:3.12",
                status="pending",
                retry_count=0,
                last_error=None,
                last_synced_at=None,
                metadata_={"reason": "manual_sync"},
                created_at=now,
                updated_at=now,
            )
        ]

    monkeypatch.setattr(cluster_routes, "save_cluster", fake_save_cluster)
    monkeypatch.setattr(cluster_routes, "list_clusters", fake_list_clusters)
    monkeypatch.setattr(cluster_routes, "save_ack_deployment", fake_save_ack_deployment)
    monkeypatch.setattr(image_routes, "save_image", fake_save_image)
    monkeypatch.setattr(image_routes, "create_distribution_plan", fake_create_distribution_plan)

    app = create_app(
        Settings(background_jobs_enabled=False, image_upload_dir=str(tmp_path))
    )
    app.dependency_overrides[db_session.get_session] = fake_session
    app.dependency_overrides[dependencies.get_current_principal] = fake_current_principal

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        cluster_response = await client.post(
            "/api/v1/admin/clusters",
            headers={"Authorization": "Bearer admin-token"},
            json={
                "name": "ack-prod",
                "region": "cn-hangzhou",
                "kind": "kubernetes",
                "provider": "aliyun_ack",
                "external_cluster_id": "ack-prod-1",
                "namespace": "opensandbox",
                "registry_url": "registry.cn-hangzhou.aliyuncs.com/osb",
                "kubeconfig_secret_ref": "secret/ack-prod-kubeconfig",
                "opensandbox_base_url": "http://opensandbox.opensandbox.svc:8080",
                "api_key_env": "ACK_PROD_OPENSANDBOX_API_KEY",
            },
        )
        assert cluster_response.status_code == 200
        assert cluster_response.json()["provider"] == "aliyun_ack"

        clusters = await client.get(
            "/api/v1/admin/clusters",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert clusters.status_code == 200
        assert clusters.json()["total"] == 1

        deployment = await client.post(
            "/api/v1/admin/ack-deployments",
            headers={"Authorization": "Bearer admin-token"},
            json={
                "runtime_backend_id": "cluster_ack",
                "aliyun_cluster_id": "ack-prod-1",
                "region": "cn-hangzhou",
                "namespace": "opensandbox",
                "vpc_id": "vpc-prod",
                "registry_url": "registry.cn-hangzhou.aliyuncs.com/osb",
                "kubeconfig_secret_ref": "secret/ack-prod-kubeconfig",
                "precheck_payload": {"storageClass": "alicloud-disk-essd"},
            },
        )
        assert deployment.status_code == 200
        assert deployment.json()["status"] == "draft"

        image = await client.post(
            "/api/v1/admin/images",
            headers={"Authorization": "Bearer admin-token"},
            json={
                "name": "python",
                "version": "3.12",
                "source_type": "manual_upload",
                "source_uri": "uploads/python-3.12.tar",
                "status": "active",
            },
        )
        assert image.status_code == 200
        assert image.json()["created_by_subject_id"] == admin.subject_id

        distributions = await client.post(
            "/api/v1/admin/images/img_test/distributions:sync",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert distributions.status_code == 200
        assert distributions.json()[0]["runtime_backend_id"] == "cluster_ack"

        upload = await client.post(
            "/api/v1/admin/images:upload?name=node&version=20&filename=node-20.tar",
            headers={
                "Authorization": "Bearer admin-token",
                "content-type": "application/octet-stream",
            },
            content=b"fake image archive",
        )
        assert upload.status_code == 200
        assert upload.json()["image"]["name"] == "node"
        assert upload.json()["distributions"][0]["status"] == "pending"
        assert (tmp_path / upload.json()["image"]["id"] / "node-20.tar").exists()


def _cluster(now: datetime, **kwargs):
    return SimpleNamespace(
        id=kwargs.get("cluster_id") or "cluster_ack",
        name=kwargs.get("name") or "ack-prod",
        region=kwargs.get("region"),
        kind=kwargs.get("kind", "kubernetes"),
        status=kwargs.get("status", "active"),
        health_status="unknown",
        provider=kwargs.get("provider", "aliyun_ack"),
        external_cluster_id=kwargs.get("external_cluster_id", "ack-prod-1"),
        namespace=kwargs.get("namespace", "opensandbox"),
        registry_url=kwargs.get("registry_url", "registry.cn-hangzhou.aliyuncs.com/osb"),
        kubeconfig_secret_ref=kwargs.get("kubeconfig_secret_ref"),
        opensandbox_base_url=kwargs.get("opensandbox_base_url", "http://opensandbox:8080"),
        api_key_env=kwargs.get("api_key_env", "ACK_PROD_OPENSANDBOX_API_KEY"),
        weight=kwargs.get("weight", 100),
        capabilities=kwargs.get("capabilities") or {},
        metadata_=kwargs.get("metadata") or {},
        last_checked_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def _image(now: datetime, **kwargs):
    return SimpleNamespace(
        id=kwargs.get("image_id") or "img_test",
        name=kwargs["name"],
        version=kwargs["version"],
        source_type=kwargs["source_type"],
        source_uri=kwargs["source_uri"],
        architecture=kwargs["architecture"],
        runtime_profile_id=kwargs["runtime_profile_id"],
        risk_level=kwargs["risk_level"],
        status=kwargs["status"],
        description=kwargs["description"],
        created_by_subject_id=kwargs["created_by_subject_id"],
        metadata_=kwargs.get("metadata") or {},
        created_at=now,
        updated_at=now,
    )

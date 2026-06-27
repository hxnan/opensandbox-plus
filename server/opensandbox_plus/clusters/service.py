from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.clusters.repository import (
    get_ack_deployment,
    get_cluster,
    list_ack_deployments as list_ack_deployments_from_db,
    list_clusters as list_clusters_from_db,
    upsert_ack_deployment,
    upsert_cluster,
)
from opensandbox_plus.db.models import AckClusterDeployment, RuntimeBackend


class ClusterServiceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def list_clusters(
    session: AsyncSession,
    *,
    status: str | None,
    provider: str | None,
    page: int,
    page_size: int,
) -> tuple[list[RuntimeBackend], int]:
    return await list_clusters_from_db(
        session,
        status=status,
        provider=provider,
        page=page,
        page_size=page_size,
    )


async def save_cluster(
    session: AsyncSession,
    *,
    cluster_id: str | None,
    name: str,
    region: str | None,
    kind: str,
    status: str,
    provider: str | None,
    external_cluster_id: str | None,
    namespace: str | None,
    registry_url: str | None,
    kubeconfig_secret_ref: str | None,
    opensandbox_base_url: str,
    api_key_env: str,
    weight: int,
    capabilities: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> RuntimeBackend:
    if weight < 0:
        raise ClusterServiceError("INVALID_REQUEST", "cluster weight must be >= 0", 400)
    try:
        return await upsert_cluster(
            session,
            cluster_id=cluster_id or f"cluster_{uuid4().hex}",
            name=name,
            region=region,
            kind=kind,
            status=status,
            health_status="unknown",
            provider=provider,
            external_cluster_id=external_cluster_id,
            namespace=namespace,
            registry_url=registry_url,
            kubeconfig_secret_ref=kubeconfig_secret_ref,
            opensandbox_base_url=opensandbox_base_url,
            api_key_env=api_key_env,
            weight=weight,
            capabilities=capabilities or {},
            metadata=metadata or {},
        )
    except IntegrityError as exc:
        await session.rollback()
        raise ClusterServiceError("CONFLICT", "cluster id or name already exists", 409) from exc


async def require_cluster(session: AsyncSession, *, cluster_id: str) -> RuntimeBackend:
    cluster = await get_cluster(session, cluster_id=cluster_id)
    if cluster is None:
        raise ClusterServiceError("NOT_FOUND", "OpenSandbox cluster not found", 404)
    return cluster


async def list_ack_deployments(
    session: AsyncSession,
    *,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AckClusterDeployment], int]:
    return await list_ack_deployments_from_db(
        session,
        status=status,
        page=page,
        page_size=page_size,
    )


async def save_ack_deployment(
    session: AsyncSession,
    *,
    deployment_id: str | None,
    runtime_backend_id: str | None,
    aliyun_cluster_id: str,
    region: str,
    namespace: str,
    vpc_id: str | None,
    registry_url: str | None,
    kubeconfig_secret_ref: str | None,
    precheck_payload: dict[str, Any] | None,
    deployment_payload: dict[str, Any] | None,
) -> AckClusterDeployment:
    if runtime_backend_id is not None:
        await require_cluster(session, cluster_id=runtime_backend_id)
    try:
        return await upsert_ack_deployment(
            session,
            deployment_id=deployment_id or f"ackdep_{uuid4().hex}",
            runtime_backend_id=runtime_backend_id,
            aliyun_cluster_id=aliyun_cluster_id,
            region=region,
            namespace=namespace,
            vpc_id=vpc_id,
            registry_url=registry_url,
            kubeconfig_secret_ref=kubeconfig_secret_ref,
            status="draft",
            precheck_payload=precheck_payload,
            deployment_payload=deployment_payload,
            last_error=None,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise ClusterServiceError("CONFLICT", "ACK deployment id already exists", 409) from exc


async def generate_ack_deployment_plan(
    session: AsyncSession,
    *,
    deployment_id: str,
) -> AckClusterDeployment:
    deployment = await get_ack_deployment(session, deployment_id=deployment_id)
    if deployment is None:
        raise ClusterServiceError("NOT_FOUND", "ACK deployment not found", 404)

    payload = _ack_deployment_plan(deployment)
    try:
        return await upsert_ack_deployment(
            session,
            deployment_id=deployment.id,
            runtime_backend_id=deployment.runtime_backend_id,
            aliyun_cluster_id=deployment.aliyun_cluster_id,
            region=deployment.region,
            namespace=deployment.namespace,
            vpc_id=deployment.vpc_id,
            registry_url=deployment.registry_url,
            kubeconfig_secret_ref=deployment.kubeconfig_secret_ref,
            status="ready",
            precheck_payload=deployment.precheck_payload,
            deployment_payload=payload,
            last_error=None,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise ClusterServiceError("CONFLICT", "failed to update ACK deployment plan", 409) from exc


def cluster_to_dict(cluster: RuntimeBackend) -> dict[str, Any]:
    return {
        "id": cluster.id,
        "name": cluster.name,
        "region": cluster.region,
        "kind": cluster.kind,
        "status": cluster.status,
        "health_status": cluster.health_status,
        "provider": cluster.provider,
        "external_cluster_id": cluster.external_cluster_id,
        "namespace": cluster.namespace,
        "registry_url": cluster.registry_url,
        "kubeconfig_secret_ref": cluster.kubeconfig_secret_ref,
        "opensandbox_base_url": cluster.opensandbox_base_url,
        "api_key_env": cluster.api_key_env,
        "weight": cluster.weight,
        "capabilities": cluster.capabilities,
        "metadata": cluster.metadata_,
        "last_checked_at": cluster.last_checked_at,
        "last_error": cluster.last_error,
        "created_at": cluster.created_at,
        "updated_at": cluster.updated_at,
    }


def ack_deployment_to_dict(deployment: AckClusterDeployment) -> dict[str, Any]:
    return {
        "id": deployment.id,
        "runtime_backend_id": deployment.runtime_backend_id,
        "aliyun_cluster_id": deployment.aliyun_cluster_id,
        "region": deployment.region,
        "namespace": deployment.namespace,
        "vpc_id": deployment.vpc_id,
        "registry_url": deployment.registry_url,
        "kubeconfig_secret_ref": deployment.kubeconfig_secret_ref,
        "status": deployment.status,
        "precheck_payload": deployment.precheck_payload,
        "deployment_payload": deployment.deployment_payload,
        "last_error": deployment.last_error,
        "created_at": deployment.created_at,
        "updated_at": deployment.updated_at,
    }


def _ack_deployment_plan(deployment: AckClusterDeployment) -> dict[str, Any]:
    namespace = deployment.namespace
    registry = deployment.registry_url.rstrip("/") if deployment.registry_url else None
    server_image = f"{registry}/opensandbox/server:latest" if registry else "opensandbox/server:latest"
    execd_image = (
        f"{registry}/opensandbox/execd:v1.0.19"
        if registry
        else "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/execd:v1.0.19"
    )
    service_name = "opensandbox-server"
    api_key_secret_name = "opensandbox-api-key"

    return {
        "kind": "opensandbox-suite-deployment-plan",
        "provider": "aliyun_ack",
        "aliyun_cluster_id": deployment.aliyun_cluster_id,
        "region": deployment.region,
        "namespace": namespace,
        "kubeconfig_secret_ref": deployment.kubeconfig_secret_ref,
        "registry_url": deployment.registry_url,
        "notes": [
            "Review manifests and replace secret placeholders before applying.",
            "This plan is generated by OpenSandbox Plus and is not applied automatically.",
        ],
        "manifests": [
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": namespace},
            },
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": api_key_secret_name, "namespace": namespace},
                "type": "Opaque",
                "stringData": {"api_key": "<replace-with-generated-opensandbox-api-key>"},
            },
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "opensandbox-config", "namespace": namespace},
                "data": {
                    "config.toml": "\n".join(
                        [
                            "[server]",
                            'host = "0.0.0.0"',
                            "port = 8090",
                            'api_key = "${OPEN_SANDBOX_API_KEY}"',
                            "",
                            "[runtime]",
                            'type = "kubernetes"',
                            f'execd_image = "{execd_image}"',
                            "",
                            "[ingress]",
                            'mode = "direct"',
                            "",
                        ]
                    )
                },
            },
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": service_name, "namespace": namespace},
                "spec": {
                    "replicas": 2,
                    "selector": {"matchLabels": {"app": service_name}},
                    "template": {
                        "metadata": {"labels": {"app": service_name}},
                        "spec": {
                            "containers": [
                                {
                                    "name": "opensandbox",
                                    "image": server_image,
                                    "ports": [{"containerPort": 8090}],
                                    "env": [
                                        {
                                            "name": "OPEN_SANDBOX_API_KEY",
                                            "valueFrom": {
                                                "secretKeyRef": {
                                                    "name": api_key_secret_name,
                                                    "key": "api_key",
                                                }
                                            },
                                        }
                                    ],
                                    "volumeMounts": [
                                        {
                                            "name": "opensandbox-config",
                                            "mountPath": "/etc/opensandbox",
                                            "readOnly": True,
                                        }
                                    ],
                                }
                            ],
                            "volumes": [
                                {
                                    "name": "opensandbox-config",
                                    "configMap": {"name": "opensandbox-config"},
                                }
                            ],
                        },
                    },
                },
            },
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": service_name, "namespace": namespace},
                "spec": {
                    "type": "ClusterIP",
                    "selector": {"app": service_name},
                    "ports": [{"name": "http", "port": 8090, "targetPort": 8090}],
                },
            },
        ],
    }

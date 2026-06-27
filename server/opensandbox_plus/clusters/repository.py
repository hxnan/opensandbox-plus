from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.db.models import AckClusterDeployment, RuntimeBackend


async def list_clusters(
    session: AsyncSession,
    *,
    status: str | None,
    provider: str | None,
    page: int,
    page_size: int,
) -> tuple[list[RuntimeBackend], int]:
    stmt: Select[tuple[RuntimeBackend]] = select(RuntimeBackend)
    count_stmt = select(func.count()).select_from(RuntimeBackend)
    if status is not None:
        stmt = stmt.where(RuntimeBackend.status == status)
        count_stmt = count_stmt.where(RuntimeBackend.status == status)
    if provider is not None:
        stmt = stmt.where(RuntimeBackend.provider == provider)
        count_stmt = count_stmt.where(RuntimeBackend.provider == provider)

    stmt = stmt.order_by(RuntimeBackend.name).offset((page - 1) * page_size).limit(page_size)
    rows = await session.scalars(stmt)
    total = int(await session.scalar(count_stmt) or 0)
    return list(rows), total


async def get_cluster(session: AsyncSession, *, cluster_id: str) -> RuntimeBackend | None:
    return await session.scalar(select(RuntimeBackend).where(RuntimeBackend.id == cluster_id))


async def upsert_cluster(
    session: AsyncSession,
    *,
    cluster_id: str,
    name: str,
    region: str | None,
    kind: str,
    status: str,
    health_status: str,
    provider: str | None,
    external_cluster_id: str | None,
    namespace: str | None,
    registry_url: str | None,
    kubeconfig_secret_ref: str | None,
    opensandbox_base_url: str,
    api_key_env: str,
    weight: int,
    capabilities: dict,
    metadata: dict,
) -> RuntimeBackend:
    stmt = (
        insert(RuntimeBackend)
        .values(
            id=cluster_id,
            name=name,
            region=region,
            kind=kind,
            status=status,
            health_status=health_status,
            provider=provider,
            external_cluster_id=external_cluster_id,
            namespace=namespace,
            registry_url=registry_url,
            kubeconfig_secret_ref=kubeconfig_secret_ref,
            opensandbox_base_url=opensandbox_base_url,
            api_key_env=api_key_env,
            weight=weight,
            capabilities=capabilities,
            metadata_=metadata,
        )
        .on_conflict_do_update(
            index_elements=[RuntimeBackend.id],
            set_={
                "name": name,
                "region": region,
                "kind": kind,
                "status": status,
                "health_status": health_status,
                "provider": provider,
                "external_cluster_id": external_cluster_id,
                "namespace": namespace,
                "registry_url": registry_url,
                "kubeconfig_secret_ref": kubeconfig_secret_ref,
                "opensandbox_base_url": opensandbox_base_url,
                "api_key_env": api_key_env,
                "weight": weight,
                "capabilities": capabilities,
                RuntimeBackend.__table__.c["metadata"]: metadata,
                "updated_at": func.now(),
            },
        )
        .returning(RuntimeBackend)
    )
    cluster = await session.scalar(stmt)
    await session.commit()
    if cluster is None:
        raise RuntimeError("failed to upsert OpenSandbox cluster")
    return cluster


async def list_ack_deployments(
    session: AsyncSession,
    *,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AckClusterDeployment], int]:
    stmt: Select[tuple[AckClusterDeployment]] = select(AckClusterDeployment)
    count_stmt = select(func.count()).select_from(AckClusterDeployment)
    if status is not None:
        stmt = stmt.where(AckClusterDeployment.status == status)
        count_stmt = count_stmt.where(AckClusterDeployment.status == status)

    stmt = (
        stmt.order_by(AckClusterDeployment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = await session.scalars(stmt)
    total = int(await session.scalar(count_stmt) or 0)
    return list(rows), total


async def upsert_ack_deployment(
    session: AsyncSession,
    *,
    deployment_id: str,
    runtime_backend_id: str | None,
    aliyun_cluster_id: str,
    region: str,
    namespace: str,
    vpc_id: str | None,
    registry_url: str | None,
    kubeconfig_secret_ref: str | None,
    status: str,
    precheck_payload: dict | None,
    deployment_payload: dict | None,
    last_error: str | None,
) -> AckClusterDeployment:
    stmt = (
        insert(AckClusterDeployment)
        .values(
            id=deployment_id,
            runtime_backend_id=runtime_backend_id,
            aliyun_cluster_id=aliyun_cluster_id,
            region=region,
            namespace=namespace,
            vpc_id=vpc_id,
            registry_url=registry_url,
            kubeconfig_secret_ref=kubeconfig_secret_ref,
            status=status,
            precheck_payload=precheck_payload,
            deployment_payload=deployment_payload,
            last_error=last_error,
        )
        .on_conflict_do_update(
            index_elements=[AckClusterDeployment.id],
            set_={
                "runtime_backend_id": runtime_backend_id,
                "aliyun_cluster_id": aliyun_cluster_id,
                "region": region,
                "namespace": namespace,
                "vpc_id": vpc_id,
                "registry_url": registry_url,
                "kubeconfig_secret_ref": kubeconfig_secret_ref,
                "status": status,
                "precheck_payload": precheck_payload,
                "deployment_payload": deployment_payload,
                "last_error": last_error,
                "updated_at": func.now(),
            },
        )
        .returning(AckClusterDeployment)
    )
    deployment = await session.scalar(stmt)
    await session.commit()
    if deployment is None:
        raise RuntimeError("failed to upsert ACK deployment")
    return deployment

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import require_platform_admin
from opensandbox_plus.api.management.schemas import (
    AckDeploymentRequest,
    AckDeploymentResponse,
    ClusterRequest,
    ClusterResponse,
    Page,
)
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.clusters.service import (
    ClusterServiceError,
    ack_deployment_to_dict,
    cluster_to_dict,
    generate_ack_deployment_plan,
    list_ack_deployments,
    list_clusters,
    save_ack_deployment,
    save_cluster,
)
from opensandbox_plus.db.session import get_session

router = APIRouter(prefix="/admin")


@router.get("/clusters", response_model=Page[ClusterResponse])
async def get_clusters(
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[ClusterResponse]:
    clusters, total = await list_clusters(
        session,
        status=status,
        provider=provider,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[ClusterResponse(**cluster_to_dict(cluster)) for cluster in clusters],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.put("/clusters/{cluster_id}", response_model=ClusterResponse)
async def put_cluster(
    cluster_id: str,
    payload: ClusterRequest,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClusterResponse:
    try:
        cluster = await save_cluster(
            session,
            cluster_id=cluster_id,
            name=payload.name,
            region=payload.region,
            kind=payload.kind,
            status=payload.status,
            provider=payload.provider,
            external_cluster_id=payload.external_cluster_id,
            namespace=payload.namespace,
            registry_url=payload.registry_url,
            kubeconfig_secret_ref=payload.kubeconfig_secret_ref,
            opensandbox_base_url=payload.opensandbox_base_url,
            api_key_env=payload.api_key_env,
            weight=payload.weight,
            capabilities=payload.capabilities,
            metadata=payload.metadata,
        )
    except ClusterServiceError as exc:
        raise _service_http_error(exc) from exc
    return ClusterResponse(**cluster_to_dict(cluster))


@router.post("/clusters", response_model=ClusterResponse)
async def post_cluster(
    payload: ClusterRequest,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClusterResponse:
    try:
        cluster = await save_cluster(
            session,
            cluster_id=None,
            name=payload.name,
            region=payload.region,
            kind=payload.kind,
            status=payload.status,
            provider=payload.provider,
            external_cluster_id=payload.external_cluster_id,
            namespace=payload.namespace,
            registry_url=payload.registry_url,
            kubeconfig_secret_ref=payload.kubeconfig_secret_ref,
            opensandbox_base_url=payload.opensandbox_base_url,
            api_key_env=payload.api_key_env,
            weight=payload.weight,
            capabilities=payload.capabilities,
            metadata=payload.metadata,
        )
    except ClusterServiceError as exc:
        raise _service_http_error(exc) from exc
    return ClusterResponse(**cluster_to_dict(cluster))


@router.get("/ack-deployments", response_model=Page[AckDeploymentResponse])
async def get_ack_deployments(
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[AckDeploymentResponse]:
    deployments, total = await list_ack_deployments(
        session,
        status=status,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[
            AckDeploymentResponse(**ack_deployment_to_dict(deployment))
            for deployment in deployments
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/ack-deployments", response_model=AckDeploymentResponse)
async def post_ack_deployment(
    payload: AckDeploymentRequest,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AckDeploymentResponse:
    try:
        deployment = await save_ack_deployment(
            session,
            deployment_id=None,
            runtime_backend_id=payload.runtime_backend_id,
            aliyun_cluster_id=payload.aliyun_cluster_id,
            region=payload.region,
            namespace=payload.namespace,
            vpc_id=payload.vpc_id,
            registry_url=payload.registry_url,
            kubeconfig_secret_ref=payload.kubeconfig_secret_ref,
            precheck_payload=payload.precheck_payload,
            deployment_payload=payload.deployment_payload,
        )
    except ClusterServiceError as exc:
        raise _service_http_error(exc) from exc
    return AckDeploymentResponse(**ack_deployment_to_dict(deployment))


@router.post("/ack-deployments/{deployment_id}/plan", response_model=AckDeploymentResponse)
async def post_ack_deployment_plan(
    deployment_id: str,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AckDeploymentResponse:
    try:
        deployment = await generate_ack_deployment_plan(
            session,
            deployment_id=deployment_id,
        )
    except ClusterServiceError as exc:
        raise _service_http_error(exc) from exc
    return AckDeploymentResponse(**ack_deployment_to_dict(deployment))


def _service_http_error(exc: ClusterServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import require_platform_admin
from opensandbox_plus.api.management.schemas import (
    ImageDistributionResponse,
    ImageDistributionStatus,
    ImageStatus,
    Page,
    SandboxImageRequest,
    SandboxImageResponse,
)
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.db.session import get_session
from opensandbox_plus.images.service import (
    ImageServiceError,
    create_distribution_plan,
    distribution_to_dict,
    image_to_dict,
    list_distributions,
    list_images,
    save_image,
)

router = APIRouter(prefix="/admin")


@router.get("/images", response_model=Page[SandboxImageResponse])
async def get_images(
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: ImageStatus | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[SandboxImageResponse]:
    images, total = await list_images(session, status=status, page=page, page_size=page_size)
    return Page(
        items=[SandboxImageResponse(**image_to_dict(image)) for image in images],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/images", response_model=SandboxImageResponse)
async def post_image(
    payload: SandboxImageRequest,
    principal: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SandboxImageResponse:
    try:
        image = await save_image(
            session,
            image_id=None,
            name=payload.name,
            version=payload.version,
            source_type=payload.source_type,
            source_uri=payload.source_uri,
            architecture=payload.architecture,
            runtime_profile_id=payload.runtime_profile_id,
            risk_level=payload.risk_level,
            status=payload.status,
            description=payload.description,
            created_by_subject_id=principal.subject_id,
            metadata=payload.metadata,
        )
    except ImageServiceError as exc:
        raise _service_http_error(exc) from exc
    return SandboxImageResponse(**image_to_dict(image))


@router.get("/image-distributions", response_model=Page[ImageDistributionResponse])
async def get_image_distributions(
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    image_id: str | None = Query(default=None),
    runtime_backend_id: str | None = Query(default=None),
    status: ImageDistributionStatus | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[ImageDistributionResponse]:
    distributions, total = await list_distributions(
        session,
        image_id=image_id,
        runtime_backend_id=runtime_backend_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[
            ImageDistributionResponse(**distribution_to_dict(distribution))
            for distribution in distributions
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/images/{image_id}/distributions:sync",
    response_model=list[ImageDistributionResponse],
)
async def post_image_distribution_sync(
    image_id: str,
    _: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ImageDistributionResponse]:
    try:
        distributions = await create_distribution_plan(session, image_id=image_id)
    except ImageServiceError as exc:
        raise _service_http_error(exc) from exc
    return [
        ImageDistributionResponse(**distribution_to_dict(distribution))
        for distribution in distributions
    ]


def _service_http_error(exc: ImageServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )

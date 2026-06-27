from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from re import sub
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.api.dependencies import require_platform_admin
from opensandbox_plus.api.management.schemas import (
    ImageDistributionResponse,
    ImageDistributionStatus,
    ImageRiskLevel,
    ImageStatus,
    Page,
    SandboxImageRequest,
    SandboxImageResponse,
    SandboxImageUploadResponse,
)
from opensandbox_plus.auth.principal import Principal
from opensandbox_plus.config import Settings
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


@router.post("/images:upload", response_model=SandboxImageUploadResponse)
async def post_image_upload(
    request: Request,
    principal: Annotated[Principal, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    name: str = Query(min_length=1, max_length=256),
    version: str = Query(min_length=1, max_length=128),
    filename: str | None = Query(default=None, max_length=256),
    architecture: str = Query(default="amd64", min_length=1, max_length=64),
    runtime_profile_id: str | None = Query(default=None, max_length=128),
    risk_level: ImageRiskLevel = Query(default="low"),
    status: ImageStatus = Query(default="active"),
    description: str | None = Query(default=None, max_length=1024),
) -> SandboxImageUploadResponse:
    settings: Settings = request.app.state.settings
    image_id = f"img_{uuid4().hex}"
    safe_name = _safe_filename(
        filename
        or request.headers.get("x-osb-filename")
        or request.headers.get("x-filename")
        or f"{name}-{version}.tar"
    )
    artifact = await _persist_upload(
        request,
        image_id=image_id,
        filename=safe_name,
        settings=settings,
    )
    try:
        image = await save_image(
            session,
            image_id=image_id,
            name=name,
            version=version,
            source_type="manual_upload",
            source_uri=artifact["source_uri"],
            architecture=architecture,
            runtime_profile_id=runtime_profile_id,
            risk_level=risk_level,
            status=status,
            description=description,
            created_by_subject_id=principal.subject_id,
            metadata={
                "upload": {
                    "filename": safe_name,
                    "size_bytes": artifact["size_bytes"],
                    "sha256": artifact["sha256"],
                    "storage_path": artifact["storage_path"],
                }
            },
        )
        distributions = await create_distribution_plan(session, image_id=image.id)
    except ImageServiceError as exc:
        _delete_upload_artifact(artifact["storage_path"])
        raise _service_http_error(exc) from exc

    return SandboxImageUploadResponse(
        image=SandboxImageResponse(**image_to_dict(image)),
        distributions=[
            ImageDistributionResponse(**distribution_to_dict(distribution))
            for distribution in distributions
        ],
    )


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


def _safe_filename(filename: str) -> str:
    sanitized = sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).name).strip(".-")
    return sanitized or "sandbox-image.tar"


async def _persist_upload(
    request: Request,
    *,
    image_id: str,
    filename: str,
    settings: Settings,
) -> dict[str, str | int]:
    upload_root = Path(settings.image_upload_dir).resolve()
    target_dir = (upload_root / image_id).resolve()
    if upload_root not in target_dir.parents:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_UPLOAD_PATH", "message": "invalid upload path"},
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    tmp_path = target_dir / f".{filename}.tmp"

    digest = sha256()
    size = 0
    try:
        with tmp_path.open("wb") as output:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > settings.image_upload_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "UPLOAD_TOO_LARGE",
                            "message": "uploaded image exceeds configured limit",
                        },
                    )
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise HTTPException(
                status_code=400,
                detail={"code": "EMPTY_UPLOAD", "message": "uploaded image is empty"},
            )
        tmp_path.replace(target_path)
    except Exception:
        _delete_upload_artifact(str(tmp_path))
        _delete_upload_artifact(str(target_path))
        raise

    return {
        "source_uri": f"local://sandbox-images/{image_id}/{filename}",
        "storage_path": str(target_path),
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    }


def _delete_upload_artifact(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        return

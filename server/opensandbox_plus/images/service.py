from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.db.models import ImageDistribution, SandboxImage
from opensandbox_plus.images.repository import (
    get_image,
    list_distribution_targets,
    list_distributions as list_distributions_from_db,
    list_images as list_images_from_db,
    upsert_distribution,
    upsert_image,
)


class ImageServiceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def list_images(
    session: AsyncSession,
    *,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[SandboxImage], int]:
    return await list_images_from_db(session, status=status, page=page, page_size=page_size)


async def save_image(
    session: AsyncSession,
    *,
    image_id: str | None,
    name: str,
    version: str,
    source_type: str,
    source_uri: str | None,
    architecture: str,
    runtime_profile_id: str | None,
    risk_level: str,
    status: str,
    description: str | None,
    created_by_subject_id: str | None,
    metadata: dict[str, Any] | None,
) -> SandboxImage:
    try:
        return await upsert_image(
            session,
            image_id=image_id or f"img_{uuid4().hex}",
            name=name,
            version=version,
            source_type=source_type,
            source_uri=source_uri,
            architecture=architecture,
            runtime_profile_id=runtime_profile_id,
            risk_level=risk_level,
            status=status,
            description=description,
            created_by_subject_id=created_by_subject_id,
            metadata=metadata or {},
        )
    except IntegrityError as exc:
        await session.rollback()
        raise ImageServiceError(
            "CONFLICT",
            "image id or name/version/architecture already exists",
            409,
        ) from exc


async def require_image(session: AsyncSession, *, image_id: str) -> SandboxImage:
    image = await get_image(session, image_id=image_id)
    if image is None:
        raise ImageServiceError("NOT_FOUND", "sandbox image not found", 404)
    return image


async def list_distributions(
    session: AsyncSession,
    *,
    image_id: str | None,
    runtime_backend_id: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[ImageDistribution], int]:
    return await list_distributions_from_db(
        session,
        image_id=image_id,
        runtime_backend_id=runtime_backend_id,
        status=status,
        page=page,
        page_size=page_size,
    )


async def create_distribution_plan(
    session: AsyncSession,
    *,
    image_id: str,
) -> list[ImageDistribution]:
    image = await require_image(session, image_id=image_id)
    targets = await list_distribution_targets(session)
    distributions: list[ImageDistribution] = []
    for target in targets:
        distributions.append(
            await upsert_distribution(
                session,
                distribution_id=f"dist_{uuid4().hex}",
                image_id=image.id,
                runtime_backend_id=target.id,
                registry_url=target.registry_url,
                target_ref=_target_ref(target.registry_url, image),
                status="pending",
                metadata={"reason": "manual_sync"},
            )
        )
    await session.commit()
    return distributions


def image_to_dict(image: SandboxImage) -> dict[str, Any]:
    return {
        "id": image.id,
        "name": image.name,
        "version": image.version,
        "source_type": image.source_type,
        "source_uri": image.source_uri,
        "architecture": image.architecture,
        "runtime_profile_id": image.runtime_profile_id,
        "risk_level": image.risk_level,
        "status": image.status,
        "description": image.description,
        "created_by_subject_id": image.created_by_subject_id,
        "metadata": image.metadata_,
        "created_at": image.created_at,
        "updated_at": image.updated_at,
    }


def distribution_to_dict(distribution: ImageDistribution) -> dict[str, Any]:
    return {
        "id": distribution.id,
        "image_id": distribution.image_id,
        "runtime_backend_id": distribution.runtime_backend_id,
        "registry_url": distribution.registry_url,
        "target_ref": distribution.target_ref,
        "status": distribution.status,
        "retry_count": distribution.retry_count,
        "last_error": distribution.last_error,
        "last_synced_at": distribution.last_synced_at,
        "metadata": distribution.metadata_,
        "created_at": distribution.created_at,
        "updated_at": distribution.updated_at,
    }


def _target_ref(registry_url: str | None, image: SandboxImage) -> str | None:
    if not registry_url:
        return None
    return f"{registry_url.rstrip('/')}/{image.name}:{image.version}"

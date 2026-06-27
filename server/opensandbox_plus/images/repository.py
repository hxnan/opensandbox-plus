from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.db.models import ImageDistribution, RuntimeBackend, SandboxImage


async def list_images(
    session: AsyncSession,
    *,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[SandboxImage], int]:
    stmt: Select[tuple[SandboxImage]] = select(SandboxImage)
    count_stmt = select(func.count()).select_from(SandboxImage)
    if status is not None:
        stmt = stmt.where(SandboxImage.status == status)
        count_stmt = count_stmt.where(SandboxImage.status == status)
    stmt = stmt.order_by(SandboxImage.name, SandboxImage.version).offset(
        (page - 1) * page_size
    ).limit(page_size)
    rows = await session.scalars(stmt)
    total = int(await session.scalar(count_stmt) or 0)
    return list(rows), total


async def get_image(session: AsyncSession, *, image_id: str) -> SandboxImage | None:
    return await session.scalar(select(SandboxImage).where(SandboxImage.id == image_id))


async def upsert_image(
    session: AsyncSession,
    *,
    image_id: str,
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
    metadata: dict,
) -> SandboxImage:
    stmt = (
        insert(SandboxImage)
        .values(
            id=image_id,
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
            metadata_=metadata,
        )
        .on_conflict_do_update(
            index_elements=[SandboxImage.id],
            set_={
                "name": name,
                "version": version,
                "source_type": source_type,
                "source_uri": source_uri,
                "architecture": architecture,
                "runtime_profile_id": runtime_profile_id,
                "risk_level": risk_level,
                "status": status,
                "description": description,
                SandboxImage.__table__.c["metadata"]: metadata,
                "updated_at": func.now(),
            },
        )
        .returning(SandboxImage)
    )
    image = await session.scalar(stmt)
    await session.commit()
    if image is None:
        raise RuntimeError("failed to upsert sandbox image")
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
    stmt: Select[tuple[ImageDistribution]] = select(ImageDistribution)
    count_stmt = select(func.count()).select_from(ImageDistribution)
    if image_id is not None:
        stmt = stmt.where(ImageDistribution.image_id == image_id)
        count_stmt = count_stmt.where(ImageDistribution.image_id == image_id)
    if runtime_backend_id is not None:
        stmt = stmt.where(ImageDistribution.runtime_backend_id == runtime_backend_id)
        count_stmt = count_stmt.where(ImageDistribution.runtime_backend_id == runtime_backend_id)
    if status is not None:
        stmt = stmt.where(ImageDistribution.status == status)
        count_stmt = count_stmt.where(ImageDistribution.status == status)

    stmt = stmt.order_by(ImageDistribution.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    rows = await session.scalars(stmt)
    total = int(await session.scalar(count_stmt) or 0)
    return list(rows), total


async def list_distribution_targets(session: AsyncSession) -> list[RuntimeBackend]:
    stmt = (
        select(RuntimeBackend)
        .where(RuntimeBackend.status == "active")
        .order_by(RuntimeBackend.name)
    )
    rows = await session.scalars(stmt)
    return list(rows)


async def upsert_distribution(
    session: AsyncSession,
    *,
    distribution_id: str,
    image_id: str,
    runtime_backend_id: str,
    registry_url: str | None,
    target_ref: str | None,
    status: str,
    metadata: dict,
) -> ImageDistribution:
    stmt = (
        insert(ImageDistribution)
        .values(
            id=distribution_id,
            image_id=image_id,
            runtime_backend_id=runtime_backend_id,
            registry_url=registry_url,
            target_ref=target_ref,
            status=status,
            metadata_=metadata,
        )
        .on_conflict_do_update(
            constraint="uq_image_distribution_backend",
            set_={
                "registry_url": registry_url,
                "target_ref": target_ref,
                "status": status,
                ImageDistribution.__table__.c["metadata"]: metadata,
                "updated_at": func.now(),
            },
        )
        .returning(ImageDistribution)
    )
    distribution = await session.scalar(stmt)
    if distribution is None:
        raise RuntimeError("failed to upsert image distribution")
    return distribution

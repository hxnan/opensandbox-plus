from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.auth.principal import CloudSandboxPrincipal
from opensandbox_plus.config import Settings
from opensandbox_plus.sandboxes.repository import (
    create_sandbox_index,
    get_owned_sandbox,
    list_owned_sandbox_ids,
    mark_sandbox_deleted,
    update_sandbox_index,
)


def extract_sandbox_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("id") or payload.get("sandboxId") or payload.get("sandbox_id")
    return value if isinstance(value, str) and value else None


def extract_state(payload: dict[str, Any]) -> str:
    status_payload = payload.get("status")
    if isinstance(status_payload, dict):
        value = status_payload.get("state")
        if isinstance(value, str) and value:
            return normalize_state(value)
    value = payload.get("state")
    return normalize_state(value) if isinstance(value, str) else "unknown"


def extract_expires_at(payload: dict[str, Any]) -> datetime | None:
    value = payload.get("expiresAt") or payload.get("expires_at")
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_image(payload: dict[str, Any], request_payload: dict[str, Any]) -> str | None:
    image = payload.get("image") or request_payload.get("image")
    if isinstance(image, str):
        return image
    if isinstance(image, dict):
        uri = image.get("uri")
        return uri if isinstance(uri, str) else None
    return None


def normalize_state(value: str) -> str:
    mapping = {
        "pending": "pending",
        "running": "running",
        "pausing": "running",
        "paused": "paused",
        "resuming": "paused",
        "stopping": "stopping",
        "stopped": "stopped",
        "terminated": "stopped",
        "failed": "failed",
        "deleted": "deleted",
    }
    return mapping.get(value.lower(), "unknown")


async def record_created_sandbox(
    session: AsyncSession,
    *,
    settings: Settings,
    principal: CloudSandboxPrincipal,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
) -> None:
    sandbox_id = extract_sandbox_id(response_payload)
    if sandbox_id is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "OPENSANDBOX_BACKEND_ERROR",
                "message": "OpenSandbox create response did not include sandbox id",
            },
        )

    try:
        await create_sandbox_index(
            session,
            settings=settings,
            public_sandbox_id=sandbox_id,
            opensandbox_id=sandbox_id,
            owner_subject_id=principal.subject_id,
            credential_id=principal.credential_id,
            image=extract_image(response_payload, request_payload),
            state=extract_state(response_payload),
            requested_timeout_seconds=_extract_timeout(request_payload),
            expires_at=extract_expires_at(response_payload),
            payload=response_payload,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "sandbox index already exists"},
        ) from exc


async def ensure_owned_sandbox(
    session: AsyncSession,
    *,
    principal: CloudSandboxPrincipal,
    sandbox_id: str,
):
    sandbox = await get_owned_sandbox(
        session,
        owner_subject_id=principal.subject_id,
        public_sandbox_id=sandbox_id,
    )
    if sandbox is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "sandbox not found"},
        )
    return sandbox


async def filter_list_payload_to_owner(
    session: AsyncSession,
    *,
    principal: CloudSandboxPrincipal,
    payload: dict[str, Any],
) -> dict[str, Any]:
    owned_ids = await list_owned_sandbox_ids(session, owner_subject_id=principal.subject_id)
    items = _extract_items(payload)
    if items is None:
        return payload

    filtered = [
        item for item in items if isinstance(item, dict) and extract_sandbox_id(item) in owned_ids
    ]
    result = dict(payload)
    if "items" in result:
        result["items"] = filtered
    elif "sandboxes" in result:
        result["sandboxes"] = filtered
    if "total" in result:
        result["total"] = len(filtered)
    return result


async def record_deleted_sandbox(
    session: AsyncSession,
    *,
    sandbox,
    payload: dict[str, Any] | None,
) -> None:
    await mark_sandbox_deleted(session, sandbox=sandbox, payload=payload)


async def record_sandbox_payload(
    session: AsyncSession,
    *,
    sandbox,
    payload: dict[str, Any],
) -> None:
    await update_sandbox_index(
        session,
        sandbox=sandbox,
        state=extract_state(payload),
        expires_at=extract_expires_at(payload),
        payload=payload,
    )


async def record_sandbox_state(
    session: AsyncSession,
    *,
    sandbox,
    state: str,
) -> None:
    await update_sandbox_index(session, sandbox=sandbox, state=state)


def _extract_items(payload: dict[str, Any]) -> list[Any] | None:
    for key in ("items", "sandboxes", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None


def _extract_timeout(payload: dict[str, Any]) -> int | None:
    value = payload.get("timeout")
    return value if isinstance(value, int) else None

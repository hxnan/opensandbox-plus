from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from opensandbox_plus.auth.constants import SANDBOX_API_KEY_HEADER
from opensandbox_plus.config import Settings
from opensandbox_plus.sandboxes.repository import ensure_default_backend
from opensandbox_plus.platform_status.repository import (
    count_active_credentials,
    count_failed_sandboxes_15m,
    count_recent_backend_errors_15m,
    count_running_sandboxes,
    list_backends,
    running_sandbox_count_by_backend,
    sandbox_state_distribution,
    update_backend_health,
)


async def get_platform_status(session: AsyncSession, settings: Settings) -> dict[str, Any]:
    await ensure_default_backend(session, settings)
    backends = await list_backends(session)

    backend_health = []
    running_by_backend = await running_sandbox_count_by_backend(session)
    for backend in backends:
        health_status, last_error = await _check_backend_health(
            backend.opensandbox_base_url,
            settings.opensandbox_internal_api_key,
        )
        await update_backend_health(
            session,
            backend_id=backend.id,
            health_status=health_status,
            last_error=last_error,
        )
        backend_health.append(
            {
                "id": backend.id,
                "name": backend.name,
                "status": backend.status,
                "health_status": health_status,
                "running_sandboxes": running_by_backend.get(backend.id, 0),
                "last_checked_at": datetime.now(UTC).isoformat(),
                "last_error": last_error,
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "backends": backend_health,
        "summary": {
            "active_credentials": await count_active_credentials(session),
            "running_sandboxes": await count_running_sandboxes(session),
            "failed_sandboxes_15m": await count_failed_sandboxes_15m(session),
            "recent_backend_errors_15m": await count_recent_backend_errors_15m(session),
            "sandbox_states": await sandbox_state_distribution(session),
        },
    }


async def list_runtime_backends(session: AsyncSession, settings: Settings) -> dict[str, Any]:
    await ensure_default_backend(session, settings)
    backends = await list_backends(session)
    items = [
        {
            "id": backend.id,
            "name": backend.name,
            "region": backend.region,
            "kind": backend.kind,
            "status": backend.status,
            "health_status": backend.health_status,
            "opensandbox_base_url": backend.opensandbox_base_url,
            "api_key_env": backend.api_key_env,
            "weight": backend.weight,
            "capabilities": backend.capabilities,
            "metadata": backend.metadata_,
            "last_checked_at": backend.last_checked_at.isoformat()
            if backend.last_checked_at
            else None,
            "last_error": backend.last_error,
            "created_at": backend.created_at.isoformat(),
            "updated_at": backend.updated_at.isoformat(),
        }
        for backend in backends
    ]
    return {"items": items, "page": 1, "page_size": len(items), "total": len(items)}


async def _check_backend_health(base_url: str, internal_api_key: str) -> tuple[str, str | None]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                base_url.rstrip("/") + "/health",
                headers={SANDBOX_API_KEY_HEADER: internal_api_key},
            )
        if response.status_code < 500:
            return "healthy", None
        return "unhealthy", f"health check returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        return "unhealthy", str(exc)

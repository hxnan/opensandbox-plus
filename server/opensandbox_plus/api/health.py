from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "service": "opensandbox-plus",
        "app_role": settings.app_role,
    }

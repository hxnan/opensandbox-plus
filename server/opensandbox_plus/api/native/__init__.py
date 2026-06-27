from __future__ import annotations

from fastapi import APIRouter

from opensandbox_plus.api.native import sandboxes

router = APIRouter(tags=["OpenSandbox Compatible API"])
router.include_router(sandboxes.router)

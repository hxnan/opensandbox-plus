from __future__ import annotations

from fastapi import APIRouter

from opensandbox_plus.api.management import admin, audit, credentials, me, quotas

router = APIRouter(tags=["Management"])
router.include_router(me.router)
router.include_router(credentials.router)
router.include_router(quotas.router)
router.include_router(audit.router)
router.include_router(admin.router, prefix="/admin")

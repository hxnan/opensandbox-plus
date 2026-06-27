from __future__ import annotations

from fastapi import APIRouter

from opensandbox_plus.api.management import admin, audit, clusters, credentials, images, me, quotas

router = APIRouter(tags=["Management"])
router.include_router(me.router)
router.include_router(credentials.router)
router.include_router(quotas.router)
router.include_router(audit.router)
router.include_router(clusters.router)
router.include_router(images.router)
router.include_router(admin.router, prefix="/admin")

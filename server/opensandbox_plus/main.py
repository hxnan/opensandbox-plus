from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from opensandbox_plus.api.casdoor_static import router as casdoor_static_router
from opensandbox_plus.api.errors import configure_error_contract
from opensandbox_plus.api.health import router as health_router
from opensandbox_plus.api.management import router as management_router
from opensandbox_plus.api.middleware import RequestIdMiddleware
from opensandbox_plus.api.native import router as native_router
from opensandbox_plus.config import Settings, get_settings
from opensandbox_plus.jobs.runner import JobRunner
from opensandbox_plus.logging import configure_structured_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    runner: JobRunner | None = None
    if settings.app_role in {"all", "worker"} and settings.background_jobs_enabled:
        runner = JobRunner(settings)
        await runner.start()
        app.state.job_runner = runner
    try:
        yield
    finally:
        if runner is not None:
            await runner.stop()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_structured_logging()
    app = FastAPI(
        title="OpenSandbox Plus",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    configure_error_contract(app)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(casdoor_static_router)

    if settings.app_role in {"all", "api"}:
        app.include_router(management_router, prefix="/api/v1")
        app.include_router(native_router)
        console_dir = Path(settings.console_static_dir)
        if console_dir.exists():
            app.mount("/", StaticFiles(directory=console_dir, html=True), name="console")

    return app


app = create_app()

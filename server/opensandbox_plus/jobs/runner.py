from __future__ import annotations

import asyncio
from contextlib import suppress

from opensandbox_plus.config import Settings


class JobRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="opensandbox-plus-jobs")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(60)

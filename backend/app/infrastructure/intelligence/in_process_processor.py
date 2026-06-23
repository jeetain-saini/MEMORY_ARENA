"""InProcessIntelligenceJobProcessor — async, in-process evolution worker.

Runs each intelligence re-evaluation (promotion + clustering for a user) as an
asyncio task so the producer (the ``MemoryCreated`` handler) returns immediately
and evolution happens off the critical path. Failures are isolated and logged;
``drain`` awaits all in-flight jobs (shutdown/tests). Identical in shape to the
embedding / graph / maintenance / consolidation processors.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.application.interfaces.intelligence_job_processor import (
    IntelligenceJob,
    IntelligenceJobProcessor,
)

_logger = logging.getLogger("memoryarena.intelligence")

JobRunner = Callable[[IntelligenceJob], Awaitable[None]]


class InProcessIntelligenceJobProcessor(IntelligenceJobProcessor):
    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def submit(self, job: IntelligenceJob) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: IntelligenceJob) -> None:
        try:
            await self._runner(job)
        except Exception:  # noqa: BLE001 - isolate background failures
            _logger.exception("intelligence.job.failed", extra={"user_id": str(job.user_id)})

    async def drain(self) -> None:
        # Loop so that tasks spawned *during* draining (e.g. a promotion that
        # dispatches MemoryCreated, re-triggering this handler) are also awaited.
        # Terminates because the cascade is bounded (promotion dedup -> no new
        # work), leaving no orphan tasks.
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

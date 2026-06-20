"""InProcessMaintenanceJobProcessor — async, in-process inference worker.

Runs each relationship-inference job as an asyncio task so the producer (the
``MemoryCreated`` event handler) returns immediately and inference happens off
the critical path. Failures are isolated and logged; ``drain`` awaits all
in-flight jobs (shutdown/tests). Identical in shape to the embedding/graph/
workflow/consolidation processors.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.application.interfaces.maintenance_job_processor import (
    InferenceJob,
    MaintenanceJobProcessor,
)

_logger = logging.getLogger("memoryarena.maintenance")

JobRunner = Callable[[InferenceJob], Awaitable[None]]


class InProcessMaintenanceJobProcessor(MaintenanceJobProcessor):
    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def submit(self, job: InferenceJob) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: InferenceJob) -> None:
        try:
            await self._runner(job)
        except Exception:  # noqa: BLE001 - isolate background failures
            _logger.exception("maintenance.job.failed", extra={"memory_id": str(job.memory_id)})

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

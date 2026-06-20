"""InProcessConsolidationJobProcessor — asyncio-based consolidation job runner.

Mirrors InProcessWorkflowJobProcessor and InProcessGraphJobProcessor exactly:
  * submit() fires an asyncio Task (non-blocking, off the event path)
  * drain() awaits all in-flight tasks before shutdown
  * exceptions in individual tasks are logged and swallowed — one bad job
    never crashes the processor or blocks other jobs
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.application.interfaces.consolidation_job_processor import (
    ConsolidationJob,
    ConsolidationJobProcessor,
)

_logger = logging.getLogger("memoryarena.consolidation")

JobRunner = Callable[[ConsolidationJob], Awaitable[None]]


class InProcessConsolidationJobProcessor(ConsolidationJobProcessor):
    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def submit(self, job: ConsolidationJob) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: ConsolidationJob) -> None:
        try:
            await self._runner(job)
        except Exception:
            _logger.exception(
                "consolidation.job.failed",
                extra={"memory_id": str(job.memory_id)},
            )

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

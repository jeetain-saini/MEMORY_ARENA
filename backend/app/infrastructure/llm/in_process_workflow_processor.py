"""InProcessWorkflowJobProcessor — async, in-process ingestion worker.

Runs each submitted job as an asyncio task in the current event loop, so the
producer (the ingest endpoint) returns immediately and extraction + persistence
happen off the critical path. Failures are isolated and logged. ``drain`` awaits
all in-flight jobs — used on shutdown and in tests for determinism.

Identical in shape to the embedding and graph processors; swapping in Celery/RQ/
Kafka is a composition-root change behind the ``WorkflowJobProcessor`` port.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.application.interfaces.workflow_job_processor import WorkflowJob, WorkflowJobProcessor

_logger = logging.getLogger("memoryarena.workflow")

JobRunner = Callable[[WorkflowJob], Awaitable[None]]


class InProcessWorkflowJobProcessor(WorkflowJobProcessor):
    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def submit(self, job: WorkflowJob) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: WorkflowJob) -> None:
        try:
            await self._runner(job)
        except Exception:  # noqa: BLE001 - isolate background failures
            _logger.exception("workflow.job.failed", extra={"job_id": str(job.job_id)})

    async def drain(self) -> None:
        """Wait for all in-flight jobs to finish."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

"""InProcessGraphJobProcessor — async, in-process knowledge-graph worker.

Runs each submitted job as an asyncio task in the current event loop, so the
producer (the graph event handler) returns immediately and graph sync happens
off the critical path. Failures are isolated and logged. ``drain`` awaits all
in-flight jobs — used on shutdown and in tests for determinism.

Future swap-ins (Celery, RQ, Kafka consumer) implement the same
``GraphJobProcessor`` port with no change to producers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.application.interfaces.graph_job_processor import GraphJobProcessor, GraphSyncJob

_logger = logging.getLogger("memoryarena.graph")

JobRunner = Callable[[GraphSyncJob], Awaitable[None]]


class InProcessGraphJobProcessor(GraphJobProcessor):
    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def submit(self, job: GraphSyncJob) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: GraphSyncJob) -> None:
        try:
            await self._runner(job)
        except Exception:  # noqa: BLE001 - isolate background failures
            _logger.exception("graph.job.failed", extra={"action": job.action.value})

    async def drain(self) -> None:
        """Wait for all in-flight jobs to finish."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

"""InProcessEmbeddingJobProcessor — async, in-process embedding worker.

Runs each submitted job as an asyncio task in the current event loop, so the
producer (an event handler) returns immediately and embedding work happens off
the critical path. Failures are isolated and logged. ``drain`` awaits all
in-flight jobs — used on shutdown and in tests for determinism.

Future swap-ins (Celery, RQ, Kafka consumer) implement the same
``EmbeddingJobProcessor`` port with no change to producers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.application.interfaces.embedding_job_processor import (
    EmbeddingJob,
    EmbeddingJobProcessor,
)

_logger = logging.getLogger("memoryarena.embeddings")

JobRunner = Callable[[EmbeddingJob], Awaitable[None]]


class InProcessEmbeddingJobProcessor(EmbeddingJobProcessor):
    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def submit(self, job: EmbeddingJob) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: EmbeddingJob) -> None:
        try:
            await self._runner(job)
        except Exception:  # noqa: BLE001 - isolate background failures
            _logger.exception("embedding.job.failed", extra={"action": job.action.value})

    async def drain(self) -> None:
        """Wait for all in-flight jobs to finish."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

"""Unit tests for InProcessConsolidationJobProcessor."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.interfaces.consolidation_job_processor import ConsolidationJob
from app.infrastructure.llm.in_process_consolidation_processor import (
    InProcessConsolidationJobProcessor,
)


def _run(coro):
    return asyncio.run(coro)


def _job() -> ConsolidationJob:
    return ConsolidationJob(memory_id=uuid4(), user_id=uuid4())


def test_submit_runs_the_job() -> None:
    async def scenario() -> None:
        seen: list[ConsolidationJob] = []

        async def runner(job: ConsolidationJob) -> None:
            seen.append(job)

        processor = InProcessConsolidationJobProcessor(runner)
        job = _job()
        await processor.submit(job)
        await processor.drain()
        assert seen == [job]

    _run(scenario())


def test_drain_awaits_many_jobs() -> None:
    async def scenario() -> None:
        count = 0

        async def runner(job: ConsolidationJob) -> None:
            nonlocal count
            await asyncio.sleep(0)
            count += 1

        processor = InProcessConsolidationJobProcessor(runner)
        for _ in range(5):
            await processor.submit(_job())
        await processor.drain()
        assert count == 5

    _run(scenario())


def test_failures_are_isolated() -> None:
    async def scenario() -> None:
        ran: list[ConsolidationJob] = []

        async def runner(job: ConsolidationJob) -> None:
            ran.append(job)
            raise RuntimeError("boom")

        processor = InProcessConsolidationJobProcessor(runner)
        await processor.submit(_job())
        await processor.drain()  # must not raise
        assert len(ran) == 1

    _run(scenario())

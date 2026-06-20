"""Unit tests for InProcessMaintenanceJobProcessor."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.interfaces.maintenance_job_processor import InferenceJob
from app.infrastructure.llm.in_process_maintenance_processor import (
    InProcessMaintenanceJobProcessor,
)


def _job() -> InferenceJob:
    return InferenceJob(memory_id=uuid4(), user_id=uuid4())


def test_submit_runs_the_job() -> None:
    seen: list[InferenceJob] = []

    async def runner(job: InferenceJob) -> None:
        seen.append(job)

    async def go() -> None:
        processor = InProcessMaintenanceJobProcessor(runner)
        await processor.submit(_job())
        await processor.drain()

    asyncio.run(go())
    assert len(seen) == 1


def test_drain_awaits_many() -> None:
    count = 0

    async def runner(job: InferenceJob) -> None:
        nonlocal count
        await asyncio.sleep(0)
        count += 1

    async def go() -> None:
        processor = InProcessMaintenanceJobProcessor(runner)
        for _ in range(5):
            await processor.submit(_job())
        await processor.drain()

    asyncio.run(go())
    assert count == 5


def test_failure_is_isolated() -> None:
    async def runner(job: InferenceJob) -> None:
        raise RuntimeError("boom")

    async def go() -> None:
        processor = InProcessMaintenanceJobProcessor(runner)
        await processor.submit(_job())
        await processor.drain()  # must not raise

    asyncio.run(go())

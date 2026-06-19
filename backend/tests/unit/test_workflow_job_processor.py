"""Unit tests for InProcessWorkflowJobProcessor (async background execution)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.interfaces.workflow_job_processor import WorkflowJob
from app.infrastructure.llm.in_process_workflow_processor import InProcessWorkflowJobProcessor


def _run(coro_fn):
    return asyncio.run(coro_fn())


def _job() -> WorkflowJob:
    return WorkflowJob(job_id=uuid4(), user_id=uuid4(), raw_text="some text")


def test_submit_runs_the_job() -> None:
    async def scenario() -> None:
        seen: list[WorkflowJob] = []

        async def runner(job: WorkflowJob) -> None:
            seen.append(job)

        processor = InProcessWorkflowJobProcessor(runner)
        job = _job()
        await processor.submit(job)
        await processor.drain()
        assert seen == [job]

    _run(scenario)


def test_drain_awaits_many_jobs() -> None:
    async def scenario() -> None:
        count = 0

        async def runner(job: WorkflowJob) -> None:
            nonlocal count
            await asyncio.sleep(0)
            count += 1

        processor = InProcessWorkflowJobProcessor(runner)
        for _ in range(5):
            await processor.submit(_job())
        await processor.drain()
        assert count == 5

    _run(scenario)


def test_failures_are_isolated() -> None:
    async def scenario() -> None:
        ran = []

        async def runner(job: WorkflowJob) -> None:
            ran.append(job)
            raise RuntimeError("boom")

        processor = InProcessWorkflowJobProcessor(runner)
        await processor.submit(_job())
        await processor.drain()  # must not raise
        assert len(ran) == 1

    _run(scenario)

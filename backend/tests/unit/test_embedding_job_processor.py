"""Tests for the in-process embedding job processor."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.interfaces.embedding_job_processor import EmbeddingAction, EmbeddingJob
from app.infrastructure.embeddings.in_process_processor import InProcessEmbeddingJobProcessor


def _job(action: EmbeddingAction = EmbeddingAction.UPSERT) -> EmbeddingJob:
    return EmbeddingJob(action, uuid4())


def test_submit_runs_job() -> None:
    async def scenario() -> None:
        seen: list[EmbeddingJob] = []

        async def runner(job: EmbeddingJob) -> None:
            seen.append(job)

        processor = InProcessEmbeddingJobProcessor(runner)
        job = _job()
        await processor.submit(job)
        await processor.drain()
        assert seen == [job]

    asyncio.run(scenario())


def test_drain_waits_for_multiple_jobs() -> None:
    async def scenario() -> None:
        seen: list[EmbeddingJob] = []

        async def runner(job: EmbeddingJob) -> None:
            await asyncio.sleep(0)  # yield control
            seen.append(job)

        processor = InProcessEmbeddingJobProcessor(runner)
        for _ in range(5):
            await processor.submit(_job())
        await processor.drain()
        assert len(seen) == 5

    asyncio.run(scenario())


def test_failing_job_is_isolated() -> None:
    async def scenario() -> None:
        survivors: list[int] = []

        async def runner(job: EmbeddingJob) -> None:
            if job.action is EmbeddingAction.DELETE:
                raise RuntimeError("boom")
            survivors.append(1)

        processor = InProcessEmbeddingJobProcessor(runner)
        await processor.submit(_job(EmbeddingAction.DELETE))
        await processor.submit(_job(EmbeddingAction.UPSERT))
        await processor.drain()  # must not raise
        assert survivors == [1]

    asyncio.run(scenario())

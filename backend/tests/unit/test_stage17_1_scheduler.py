"""Stage 17.1: the in-process scheduler ticker fires registered jobs
automatically when an interval is configured (the periodic-autonomy driver)."""

from __future__ import annotations

import asyncio

from app.application.interfaces.scheduler import ScheduledJob
from app.infrastructure.scheduler.in_process_scheduler import InProcessScheduler


class _CountingJob(ScheduledJob):
    name = "counting"

    def __init__(self) -> None:
        self.runs = 0

    async def run(self) -> None:
        self.runs += 1


def test_ticker_disabled_by_default_runs_nothing() -> None:
    async def scenario() -> None:
        job = _CountingJob()
        scheduler = InProcessScheduler()  # interval 0 -> no ticker
        scheduler.register(job, cron="* * * * *")
        await scheduler.start()
        await asyncio.sleep(0.05)
        await scheduler.stop()
        assert job.runs == 0  # nothing fires without a driver

    asyncio.run(scenario())


def test_ticker_fires_jobs_automatically() -> None:
    async def scenario() -> None:
        job = _CountingJob()
        scheduler = InProcessScheduler(interval_seconds=0.02)
        scheduler.register(job, cron="* * * * *")
        await scheduler.start()
        await asyncio.sleep(0.11)  # ~5 intervals
        await scheduler.stop()
        assert job.runs >= 2  # fired automatically, no explicit run_all

    asyncio.run(scenario())

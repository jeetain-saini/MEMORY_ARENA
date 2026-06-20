"""Unit tests for InProcessScheduler."""

from __future__ import annotations

import asyncio

import pytest

from app.application.interfaces.scheduler import ScheduledJob
from app.infrastructure.scheduler.in_process_scheduler import InProcessScheduler


class _RecordingJob(ScheduledJob):
    def __init__(self, name: str) -> None:
        self.name = name
        self.runs = 0

    async def run(self) -> None:
        self.runs += 1


class _FailingJob(ScheduledJob):
    name = "boom"

    def __init__(self) -> None:
        self.runs = 0

    async def run(self) -> None:
        self.runs += 1
        raise RuntimeError("kaboom")


def test_register_records_cron_and_name() -> None:
    sched = InProcessScheduler()
    sched.register(_RecordingJob("a"), cron="0 0 * * *")
    assert sched.jobs() == ["a"]
    assert sched.cron_for("a") == "0 0 * * *"


def test_run_job_invokes_named_job() -> None:
    sched = InProcessScheduler()
    job = _RecordingJob("a")
    sched.register(job, cron="* * * * *")
    asyncio.run(sched.run_job("a"))
    assert job.runs == 1


def test_run_job_unknown_raises() -> None:
    sched = InProcessScheduler()
    with pytest.raises(KeyError):
        asyncio.run(sched.run_job("missing"))


def test_run_all_runs_every_job() -> None:
    sched = InProcessScheduler()
    a, b = _RecordingJob("a"), _RecordingJob("b")
    sched.register(a, cron="* * * * *")
    sched.register(b, cron="* * * * *")
    asyncio.run(sched.run_all())
    assert a.runs == 1 and b.runs == 1


def test_failing_job_is_isolated() -> None:
    sched = InProcessScheduler()
    bad, good = _FailingJob(), _RecordingJob("good")
    sched.register(bad, cron="* * * * *")
    sched.register(good, cron="* * * * *")
    # run_all must not raise even though one job fails.
    asyncio.run(sched.run_all())
    assert bad.runs == 1 and good.runs == 1


def test_start_stop_lifecycle() -> None:
    sched = InProcessScheduler()

    async def go() -> None:
        await sched.start()
        assert sched.is_running
        await sched.stop()
        assert not sched.is_running

    asyncio.run(go())

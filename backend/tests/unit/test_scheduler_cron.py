"""Phase 1: true cron-aware scheduler execution.

Proves cron expressions stored at registration are respected (hourly runs
hourly, daily runs daily) and that a sub-minute tick never double-fires."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.application.interfaces.scheduler import ScheduledJob
from app.infrastructure.scheduler.cron import cron_matches
from app.infrastructure.scheduler.in_process_scheduler import InProcessScheduler


# --- cron matcher ----------------------------------------------------------
def test_cron_matches_hourly() -> None:
    expr = "0 * * * *"  # top of every hour
    assert cron_matches(expr, datetime(2026, 6, 23, 14, 0, tzinfo=timezone.utc)) is True
    assert cron_matches(expr, datetime(2026, 6, 23, 14, 1, tzinfo=timezone.utc)) is False


def test_cron_matches_daily_at_2am() -> None:
    expr = "0 2 * * *"
    assert cron_matches(expr, datetime(2026, 6, 23, 2, 0, tzinfo=timezone.utc)) is True
    assert cron_matches(expr, datetime(2026, 6, 23, 3, 0, tzinfo=timezone.utc)) is False
    assert cron_matches(expr, datetime(2026, 6, 23, 2, 1, tzinfo=timezone.utc)) is False


def test_cron_matches_step_and_list_and_range() -> None:
    assert cron_matches("*/15 * * * *", datetime(2026, 6, 23, 9, 30, tzinfo=timezone.utc)) is True
    assert cron_matches("*/15 * * * *", datetime(2026, 6, 23, 9, 31, tzinfo=timezone.utc)) is False
    assert cron_matches("0 9,17 * * *", datetime(2026, 6, 23, 17, 0, tzinfo=timezone.utc)) is True
    assert cron_matches("0 9-11 * * *", datetime(2026, 6, 23, 10, 0, tzinfo=timezone.utc)) is True
    assert cron_matches("0 9-11 * * *", datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)) is False


def test_cron_matches_day_of_week_sunday() -> None:
    # 2026-06-21 is a Sunday.
    sunday = datetime(2026, 6, 21, 2, 0, tzinfo=timezone.utc)
    monday = datetime(2026, 6, 22, 2, 0, tzinfo=timezone.utc)
    assert cron_matches("0 2 * * 0", sunday) is True
    assert cron_matches("0 2 * * 7", sunday) is True  # 7 also = Sunday
    assert cron_matches("0 2 * * 0", monday) is False


# --- run_due dedupe + cron respect -----------------------------------------
class _CountingJob(ScheduledJob):
    def __init__(self, name: str) -> None:
        self.name = name
        self.runs = 0

    async def run(self) -> None:
        self.runs += 1


def test_run_due_respects_cron_and_dedupes_within_minute() -> None:
    async def scenario() -> None:
        hourly = _CountingJob("hourly")
        daily = _CountingJob("daily")
        sched = InProcessScheduler()
        sched.register(hourly, cron="0 * * * *")
        sched.register(daily, cron="0 2 * * *")

        at_2am = datetime(2026, 6, 23, 2, 0, tzinfo=timezone.utc)
        # Many ticks within the same minute -> each job fires at most once.
        for _ in range(5):
            await sched.run_due(at_2am)
        assert hourly.runs == 1  # 2:00 is top of the hour
        assert daily.runs == 1   # 2:00 daily

        # A non-matching minute fires nothing new.
        await sched.run_due(datetime(2026, 6, 23, 2, 1, tzinfo=timezone.utc))
        assert hourly.runs == 1 and daily.runs == 1

        # Next hour: hourly fires again, daily does not.
        await sched.run_due(datetime(2026, 6, 23, 3, 0, tzinfo=timezone.utc))
        assert hourly.runs == 2
        assert daily.runs == 1

    asyncio.run(scenario())


def test_cron_ticker_fires_due_job_only(monkeypatch=None) -> None:
    async def scenario() -> None:
        # Clock pinned to a matching minute; tick quickly to prove the cron
        # ticker path runs the due job and dedupes it.
        now = datetime(2026, 6, 23, 2, 0, tzinfo=timezone.utc)
        job = _CountingJob("daily")
        sched = InProcessScheduler(cron_tick_seconds=0.01, clock=lambda: now)
        sched.register(job, cron="0 2 * * *")
        await sched.start()
        await asyncio.sleep(0.06)  # several ticks, same pinned minute
        await sched.stop()
        assert job.runs == 1  # cron-aware + deduped, not once-per-tick

    asyncio.run(scenario())

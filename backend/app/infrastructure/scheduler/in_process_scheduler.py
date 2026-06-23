"""InProcessScheduler — register and trigger recurring maintenance jobs.

Implements the ``Scheduler`` port as a simple in-process registry. Jobs are
registered with a cron expression (stored as metadata for a future driver) and
triggered explicitly via ``run_job`` / ``run_all`` — which keeps maintenance
fully deterministic and offline-testable.

``start``/``stop`` are provided for the port contract and to optionally drive a
lightweight interval ticker in a real deployment; the ticker is **off by
default** so tests and dev never depend on wall-clock timing. Job failures are
isolated and logged so one bad job never stops the others.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.interfaces.metrics_sink import MetricsSink
from app.application.interfaces.scheduler import ScheduledJob, Scheduler
from app.infrastructure.scheduler.cron import cron_matches

_logger = logging.getLogger("memoryarena.scheduler")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Registration:
    job: ScheduledJob
    cron: str


class InProcessScheduler(Scheduler):
    def __init__(
        self,
        *,
        interval_seconds: float = 0.0,
        cron_tick_seconds: float = 0.0,
        clock: Callable[[], datetime] = _utcnow,
        metrics: MetricsSink | None = None,
    ) -> None:
        self._registry: dict[str, _Registration] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        # Two mutually-exclusive drivers (cron preferred when both are set):
        #   * cron_tick_seconds > 0 -> evaluate each job's cron every tick and
        #     fire only the due ones (true cron-aware execution, Phase 1);
        #   * interval_seconds   > 0 -> legacy "run everything every N seconds".
        # 0/0 (default) keeps the scheduler explicitly driven (run_job/run_all).
        self._interval = interval_seconds
        self._cron_tick_seconds = cron_tick_seconds
        self._clock = clock
        self._metrics = metrics
        # Minute-resolution guard so a job fires at most once per matching minute
        # (prevents double execution when the tick is sub-minute).
        self._last_run: dict[str, str] = {}

    # -- registration ------------------------------------------------------
    def register(self, job: ScheduledJob, *, cron: str) -> None:
        self._registry[job.name] = _Registration(job=job, cron=cron)

    def jobs(self) -> list[str]:
        return list(self._registry)

    def cron_for(self, name: str) -> str:
        return self._registry[name].cron

    # -- explicit triggering (deterministic; used in tests & by a driver) --
    async def run_job(self, name: str) -> None:
        registration = self._registry.get(name)
        if registration is None:
            raise KeyError(f"unknown job: {name}")
        await self._safe_run(registration.job)

    async def run_all(self) -> None:
        for registration in list(self._registry.values()):
            await self._safe_run(registration.job)

    async def run_due(self, now: datetime | None = None) -> None:
        """Run every job whose cron is due at ``now``, at most once per minute.

        Cron-aware execution (Phase 1): respects the cron stored at registration
        and dedupes within the matching minute, so a sub-minute tick never
        double-fires and a daily job runs daily (not every tick).
        """
        now = now or self._clock()
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        for registration in list(self._registry.values()):
            if not cron_matches(registration.cron, now):
                continue
            if self._last_run.get(registration.job.name) == minute_key:
                continue  # already fired this minute -> no double execution
            self._last_run[registration.job.name] = minute_key
            await self._safe_run(registration.job)

    async def _safe_run(self, job: ScheduledJob) -> None:
        start = self._clock()
        try:
            await job.run()
            if self._metrics is not None:
                self._metrics.incr("scheduler.jobs_run_total")
        except Exception:  # noqa: BLE001 — isolate a failing job from the rest
            if self._metrics is not None:
                self._metrics.incr("scheduler.jobs_failed_total")
            _logger.exception("scheduler.job.failed", extra={"job": job.name})
        finally:
            if self._metrics is not None:
                elapsed_ms = (self._clock() - start).total_seconds() * 1000.0
                self._metrics.observe(f"scheduler.job_duration_ms.{job.name}", elapsed_ms)

    # -- lifecycle (port contract) -----------------------------------------
    async def start(self) -> None:
        """Mark the scheduler running; start the ticker when an interval is set.

        With ``interval_seconds == 0`` (default) no live ticker runs and
        execution stays explicit (``run_job``/``run_all``). With a positive
        interval, a background task fires ``run_all`` every interval — the
        offline-friendly autonomy driver for Stage 17.1.
        """
        self._running = True
        if self._task is not None:
            return
        if self._cron_tick_seconds > 0:
            self._task = asyncio.create_task(self._cron_ticker())
        elif self._interval > 0:
            self._task = asyncio.create_task(self._ticker())

    async def _cron_ticker(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._cron_tick_seconds)
                if self._running:
                    await self.run_due(self._clock())
        except asyncio.CancelledError:  # graceful shutdown
            pass

    async def _ticker(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._interval)
                if self._running:
                    await self.run_all()
        except asyncio.CancelledError:  # graceful shutdown
            pass

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    @property
    def is_running(self) -> bool:
        return self._running

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
from dataclasses import dataclass

from app.application.interfaces.scheduler import ScheduledJob, Scheduler

_logger = logging.getLogger("memoryarena.scheduler")


@dataclass(frozen=True)
class _Registration:
    job: ScheduledJob
    cron: str


class InProcessScheduler(Scheduler):
    def __init__(self, *, interval_seconds: float = 0.0) -> None:
        self._registry: dict[str, _Registration] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        # >0 drives a simple in-process ticker (Stage 17.1 autonomy); 0 keeps the
        # scheduler explicitly driven via run_job/run_all (default).
        self._interval = interval_seconds

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

    async def _safe_run(self, job: ScheduledJob) -> None:
        try:
            await job.run()
        except Exception:  # noqa: BLE001 — isolate a failing job from the rest
            _logger.exception("scheduler.job.failed", extra={"job": job.name})

    # -- lifecycle (port contract) -----------------------------------------
    async def start(self) -> None:
        """Mark the scheduler running; start the ticker when an interval is set.

        With ``interval_seconds == 0`` (default) no live ticker runs and
        execution stays explicit (``run_job``/``run_all``). With a positive
        interval, a background task fires ``run_all`` every interval — the
        offline-friendly autonomy driver for Stage 17.1.
        """
        self._running = True
        if self._interval > 0 and self._task is None:
            self._task = asyncio.create_task(self._ticker())

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

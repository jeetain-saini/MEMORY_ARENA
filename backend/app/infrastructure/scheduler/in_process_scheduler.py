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
    def __init__(self) -> None:
        self._registry: dict[str, _Registration] = {}
        self._task: asyncio.Task | None = None
        self._running = False

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
        """Mark the scheduler running. No live ticker is started by default.

        A production driver may override/extend this to drive cron schedules;
        the offline default keeps execution explicit (``run_job``/``run_all``).
        """
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    @property
    def is_running(self) -> bool:
        return self._running

"""Scheduler abstraction (interfaces only — no implementation yet).

Defines the contract for running recurring background jobs that drive memory
evolution at scale: nightly recency decay, an archival sweep, and a promotion
sweep. Stage 5 ships the *ports* only; a concrete scheduler (APScheduler, Celery
beat, Kubernetes CronJob, etc.) is a later infrastructure choice plugged in
behind these abstractions.

The job classes are abstract: they declare intent and the data each needs, but
``run`` is left unimplemented on purpose.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ScheduledJob(ABC):
    """A unit of recurring work."""

    #: Stable identifier used for registration/observability.
    name: str = "job"

    @abstractmethod
    async def run(self) -> None:
        """Execute one invocation of the job."""


class Scheduler(ABC):
    """Registers jobs against schedules and controls the run loop."""

    @abstractmethod
    def register(self, job: ScheduledJob, *, cron: str) -> None:
        """Register ``job`` to run on the given cron expression."""

    @abstractmethod
    async def start(self) -> None:
        """Begin executing registered jobs on their schedules."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the scheduler and drain in-flight jobs."""


# --- Future job contracts (interfaces only) --------------------------------
class DecaySweepJob(ScheduledJob):
    """Nightly: apply recency decay across active memories. (Stage 6+)"""

    name = "decay_sweep"


class ArchivalSweepJob(ScheduledJob):
    """Periodic: archive low-value, long-idle memories. (Stage 6+)"""

    name = "archival_sweep"


class PromotionSweepJob(ScheduledJob):
    """Periodic: promote memories that have crossed the score threshold. (Stage 6+)"""

    name = "promotion_sweep"

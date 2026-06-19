"""Tests for the scheduler abstraction (interfaces only)."""

from __future__ import annotations

import inspect

from app.application.interfaces.scheduler import (
    ArchivalSweepJob,
    DecaySweepJob,
    PromotionSweepJob,
    ScheduledJob,
    Scheduler,
)


def test_scheduler_is_abstract() -> None:
    assert inspect.isabstract(Scheduler)
    assert inspect.isabstract(ScheduledJob)


def test_future_jobs_are_declared_with_names() -> None:
    assert DecaySweepJob.name == "decay_sweep"
    assert ArchivalSweepJob.name == "archival_sweep"
    assert PromotionSweepJob.name == "promotion_sweep"
    # They remain abstract until a Stage 6 implementation provides run().
    for job in (DecaySweepJob, ArchivalSweepJob, PromotionSweepJob):
        assert issubclass(job, ScheduledJob)
        assert inspect.isabstract(job)

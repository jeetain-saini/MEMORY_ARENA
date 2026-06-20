"""Integration tests for the scheduled memory-evolution sweeps (SQLite)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import UUID

from app.application.services.maintenance.sweeps import (
    ArchivalSweepJob,
    DecaySweepJob,
    PromotionSweepJob,
)
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def _low_score() -> MemoryScore:
    return MemoryScore(importance=0.1, utility=0.1, frequency=0.0, recency=0.1, confidence=0.1)


def _high_score() -> MemoryScore:
    return MemoryScore(importance=0.9, utility=0.9, frequency=0.9, recency=0.9, confidence=0.9)


async def _ctx():
    engine = await make_engine()
    factory = create_session_factory(engine)
    dispatcher = InProcessEventDispatcher()

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    def intelligence_factory() -> MemoryIntelligenceService:
        return MemoryIntelligenceService(uow_factory(), dispatcher)

    return engine, uow_factory, intelligence_factory


async def _save(uow_factory, user_id: UUID, content: str, *, score: MemoryScore, mtype=MemoryType.FACT) -> Memory:
    memory = Memory.create(user_id=user_id, content=content, memory_type=mtype, score=score)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


async def _get(uow_factory, memory_id: UUID) -> Memory:
    async with uow_factory() as uow:
        memory = await uow.memories.get_by_id(memory_id)
    assert memory is not None
    return memory


# --- DecaySweepJob ---------------------------------------------------------

def test_decay_sweep_decays_active_memories() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        memory = await _save(uow_factory, user, "decays", score=MemoryScore())
        future = lambda: datetime.now(timezone.utc) + timedelta(days=30)  # noqa: E731
        job = DecaySweepJob(uow_factory, intel, now_fn=future)

        result = await job.run_sweep()
        assert result.processed == 1
        stored = await _get(uow_factory, memory.id)
        assert stored.score.recency < 1.0
        await engine.dispose()

    _run(scenario)


def test_decay_sweep_is_idempotent_within_period() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        memory = await _save(uow_factory, user, "decays once", score=MemoryScore())
        future = lambda: datetime(2026, 7, 1, tzinfo=timezone.utc)  # noqa: E731
        job = DecaySweepJob(uow_factory, intel, now_fn=future)

        first = await job.run_sweep()
        recency_after_first = (await _get(uow_factory, memory.id)).score.recency
        second = await job.run_sweep()
        recency_after_second = (await _get(uow_factory, memory.id)).score.recency

        assert first.processed == 1
        assert second.processed == 0 and second.skipped == 1  # period-stamp guard
        assert recency_after_first == recency_after_second  # decayed once, not twice
        await engine.dispose()

    _run(scenario)


def test_decay_sweep_resumes_next_period() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        memory = await _save(uow_factory, user, "decays each period", score=MemoryScore())

        day1 = DecaySweepJob(uow_factory, intel, now_fn=lambda: datetime(2026, 7, 1, tzinfo=timezone.utc))
        day2 = DecaySweepJob(uow_factory, intel, now_fn=lambda: datetime(2026, 7, 2, tzinfo=timezone.utc))
        await day1.run_sweep()
        r1 = (await _get(uow_factory, memory.id)).score.recency
        second = await day2.run_sweep()
        r2 = (await _get(uow_factory, memory.id)).score.recency

        assert second.processed == 1  # new period → processed again
        assert r2 < r1
        await engine.dispose()

    _run(scenario)


# --- ArchivalSweepJob ------------------------------------------------------

def test_archival_sweep_archives_low_idle_memories() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        memory = await _save(uow_factory, user, "stale", score=_low_score())
        future = lambda: datetime.now(timezone.utc) + timedelta(days=40)  # noqa: E731
        job = ArchivalSweepJob(uow_factory, intel, now_fn=future)

        result = await job.run_sweep()
        assert result.processed == 1
        assert (await _get(uow_factory, memory.id)).status is MemoryStatus.ARCHIVED
        await engine.dispose()

    _run(scenario)


def test_archival_sweep_skips_high_value() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        memory = await _save(uow_factory, user, "valuable", score=_high_score())
        future = lambda: datetime.now(timezone.utc) + timedelta(days=40)  # noqa: E731
        job = ArchivalSweepJob(uow_factory, intel, now_fn=future)

        result = await job.run_sweep()
        assert result.processed == 0 and result.skipped == 1
        assert (await _get(uow_factory, memory.id)).status is MemoryStatus.ACTIVE
        await engine.dispose()

    _run(scenario)


def test_archival_sweep_is_idempotent() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        await _save(uow_factory, user, "stale", score=_low_score())
        future = lambda: datetime.now(timezone.utc) + timedelta(days=40)  # noqa: E731
        job = ArchivalSweepJob(uow_factory, intel, now_fn=future)

        first = await job.run_sweep()
        second = await job.run_sweep()
        assert first.processed == 1
        assert second.processed == 0  # already archived → out of the ACTIVE scan
        await engine.dispose()

    _run(scenario)


# --- PromotionSweepJob -----------------------------------------------------

def test_promotion_sweep_promotes_high_value() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        memory = await _save(uow_factory, user, "promote me", score=_high_score())
        job = PromotionSweepJob(uow_factory, intel)

        result = await job.run_sweep()
        assert result.processed == 1
        stored = await _get(uow_factory, memory.id)
        assert stored.is_promoted and stored.priority == 1
        await engine.dispose()

    _run(scenario)


def test_promotion_sweep_skips_below_threshold() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        await _save(uow_factory, user, "meh", score=_low_score())
        job = PromotionSweepJob(uow_factory, intel)
        result = await job.run_sweep()
        assert result.processed == 0 and result.skipped == 1
        await engine.dispose()

    _run(scenario)


def test_promotion_sweep_is_idempotent() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user = await seed_user(engine)
        memory = await _save(uow_factory, user, "promote once", score=_high_score())
        job = PromotionSweepJob(uow_factory, intel)

        await job.run_sweep()
        second = await job.run_sweep()
        assert second.processed == 0  # not double-promoted
        assert (await _get(uow_factory, memory.id)).priority == 1
        await engine.dispose()

    _run(scenario)


# --- tenant awareness ------------------------------------------------------

def test_sweeps_are_tenant_aware() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel = await _ctx()
        user_a = await seed_user(engine)
        user_b = await seed_user(engine)
        await _save(uow_factory, user_a, "promote A", score=_high_score())
        await _save(uow_factory, user_b, "promote B", score=_high_score())
        job = PromotionSweepJob(uow_factory, intel)

        result = await job.run_sweep()
        assert result.tenants == 2
        assert result.processed == 2

        # Scoped run touches one tenant only.
        memory_c = await _save(uow_factory, user_a, "promote A2", score=_high_score())
        scoped = await job.run_sweep(user_id=user_a)
        assert scoped.tenants == 1
        assert (await _get(uow_factory, memory_c.id)).is_promoted
        await engine.dispose()

    _run(scenario)

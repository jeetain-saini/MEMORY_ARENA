"""Stage 18.3 distributed-locking tests.

Proves the lock contract (acquire / renew / release / expiry) on the in-memory
adapter and that the intelligence maintenance job runs single-owner: a second
runner that cannot take the lock skips its tick instead of double-running the
cycle. The Redis adapter shares this contract and is verified against live Redis.

SQLite + in-memory graph + dispatcher (same harness as the Stage 17/18 suites).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.application.services.intelligence.maintenance_job import (
    MemoryIntelligenceMaintenanceJob,
)
from app.application.services.locking import single_owner
from app.application.services.observability.frozen_clock import FrozenClock
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.locks.in_memory_lock import InMemoryDistributedLock
from app.infrastructure.observability.in_memory_metrics import InMemoryMetricsSink
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def _factory(engine) -> Callable[[], SQLAlchemyUnitOfWork]:
    sf = create_session_factory(engine)
    return lambda: SQLAlchemyUnitOfWork(sf)


# --- 1. lock contract ------------------------------------------------------

def test_lock_is_exclusive_and_reacquirable_after_release() -> None:
    async def scenario() -> None:
        lock = InMemoryDistributedLock(FrozenClock(epoch=1000))
        token = await lock.acquire("job", ttl_seconds=60)
        assert token is not None
        # A second acquire while held is refused.
        assert await lock.acquire("job", ttl_seconds=60) is None
        # Release frees it; it can be taken again (new token).
        assert await lock.release("job", token) is True
        token2 = await lock.acquire("job", ttl_seconds=60)
        assert token2 is not None and token2 != token

    _run(scenario)


def test_lock_renew_and_release_require_ownership() -> None:
    async def scenario() -> None:
        lock = InMemoryDistributedLock(FrozenClock(epoch=1000))
        token = await lock.acquire("job", ttl_seconds=60)
        assert token is not None
        # Owner can renew; a wrong token cannot renew or release.
        assert await lock.renew("job", token, ttl_seconds=60) is True
        assert await lock.renew("job", "not-the-owner", ttl_seconds=60) is False
        assert await lock.release("job", "not-the-owner") is False
        # Still held by the real owner.
        assert await lock.acquire("job", ttl_seconds=60) is None

    _run(scenario)


def test_lock_expires_after_ttl() -> None:
    async def scenario() -> None:
        clock = FrozenClock(epoch=1000)
        lock = InMemoryDistributedLock(clock)
        token = await lock.acquire("job", ttl_seconds=30)
        assert token is not None
        # Before expiry: still held.
        clock.advance(29)
        assert await lock.acquire("job", ttl_seconds=30) is None
        # After expiry: a new owner can take it; the stale owner cannot renew.
        clock.advance(2)  # now 31s elapsed > 30s TTL
        new_token = await lock.acquire("job", ttl_seconds=30)
        assert new_token is not None
        assert await lock.renew("job", token, ttl_seconds=30) is False

    _run(scenario)


def test_single_owner_yields_none_when_held() -> None:
    async def scenario() -> None:
        lock = InMemoryDistributedLock(FrozenClock(epoch=1000))
        held = await lock.acquire("job", ttl_seconds=60)
        assert held is not None
        async with single_owner(lock, "job", ttl_seconds=60) as lease:
            assert lease is None  # someone else holds it -> skip
        # A free key yields a working lease and releases it on exit.
        await lock.release("job", held)
        async with single_owner(lock, "job", ttl_seconds=60) as lease:
            assert lease is not None
            assert await lease.renew() is True
        # Released on exit -> acquirable again.
        assert await lock.acquire("job", ttl_seconds=60) is not None

    _run(scenario)


# --- 2. single-owner maintenance -------------------------------------------

def test_maintenance_skips_when_lock_already_held() -> None:
    """A maintenance run whose lock is held by another owner does no work."""
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        dispatcher = InProcessEventDispatcher()
        clock = FrozenClock(epoch=1000)
        lock = InMemoryDistributedLock(clock)
        metrics = InMemoryMetricsSink()

        # Recurring episodic memories that WOULD be promoted if the cycle ran.
        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content="I am learning Rust",
                                            memory_type=MemoryType.EXPERIENCE))

        job = MemoryIntelligenceMaintenanceJob(
            uowf, graph, dispatcher, metrics=metrics,
            lock=lock, lock_key="intelligence:maintenance", lock_ttl_seconds=300,
        )

        # Another instance owns the lock -> this run must skip.
        other = await lock.acquire("intelligence:maintenance", ttl_seconds=300)
        assert other is not None
        await job.run()

        async with uowf() as uow:
            mem = await uow.memories.list_for_analytics(user)
        semantic = [m for m in mem if m.category is MemoryCategory.SEMANTIC]
        assert semantic == []  # nothing promoted — the cycle was skipped
        assert metrics.snapshot().counters.get("intelligence_maintenance_skipped_total") == 1

        # Once the other owner releases, the next run proceeds and promotes.
        await lock.release("intelligence:maintenance", other)
        await job.run()
        async with uowf() as uow:
            mem = await uow.memories.list_for_analytics(user)
        assert any(m.category is MemoryCategory.SEMANTIC for m in mem)
        await engine.dispose()

    _run(scenario)


async def _save(uow_factory, memory: Memory) -> None:
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()

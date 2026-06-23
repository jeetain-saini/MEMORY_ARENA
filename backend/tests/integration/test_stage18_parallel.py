"""Stage 18.4 parallel-execution tests.

Proves the bounded-concurrency primitive (order preserved, ceiling enforced,
real overlap) and that the intelligence maintenance cycle produces identical
results whether tenants run sequentially (max_concurrency=1) or in parallel
(max_concurrency>1).

SQLite + in-memory graph + dispatcher (same harness as the Stage 17/18 suites).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import UUID

import pytest

from app.application.services.concurrency import bounded_gather, chunked
from app.application.services.intelligence.maintenance_job import (
    MemoryIntelligenceMaintenanceJob,
)
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def _factory(engine) -> Callable[[], SQLAlchemyUnitOfWork]:
    sf = create_session_factory(engine)
    return lambda: SQLAlchemyUnitOfWork(sf)


async def _save(uow_factory, memory: Memory) -> None:
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()


# --- 1. bounded_gather primitive -------------------------------------------

def test_bounded_gather_preserves_order_and_enforces_ceiling() -> None:
    async def scenario() -> None:
        in_flight = 0
        peak = 0

        async def work(i: int) -> int:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.005)  # force overlap among admitted coroutines
            in_flight -= 1
            return i

        factories = [lambda i=i: work(i) for i in range(12)]
        results = await bounded_gather(factories, limit=4)

        assert results == list(range(12))  # order preserved
        assert peak == 4                    # exactly the ceiling ran concurrently

    _run(scenario)


def test_bounded_gather_sequential_when_limit_one() -> None:
    async def scenario() -> None:
        peak = 0
        in_flight = 0

        async def work(i: int) -> int:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.001)
            in_flight -= 1
            return i

        results = await bounded_gather([lambda i=i: work(i) for i in range(5)], limit=1)
        assert results == list(range(5))
        assert peak == 1  # never more than one in flight

    _run(scenario)


def test_bounded_gather_rejects_bad_limit() -> None:
    async def scenario() -> None:
        with pytest.raises(ValueError):
            await bounded_gather([], limit=0)

    _run(scenario)


def test_chunked_splits_into_bounded_pieces() -> None:
    assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert chunked([], 3) == []
    assert chunked([1], 5) == [[1]]
    with pytest.raises(ValueError):
        chunked([1, 2], 0)


# --- 2. maintenance equivalence across concurrency -------------------------

async def _seed_tenants(uowf, n_tenants: int, engine) -> list[UUID]:
    """Each tenant gets recurring episodic memories (promotable) + a stale isolated one."""
    old = datetime.now(timezone.utc) - timedelta(days=200)
    users: list[UUID] = []
    for t in range(n_tenants):
        user = await seed_user(engine)
        users.append(user)
        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content=f"learning topic{t} deeply",
                                            memory_type=MemoryType.EXPERIENCE))
        stale = Memory.create(user_id=user, content=f"obsolete{t}", memory_type=MemoryType.FACT)
        stale.score = MemoryScore(importance=0.1, utility=0.1, frequency=0.0,
                                  recency=0.0, confidence=0.5)
        stale.updated_at = old
        await _save(uowf, stale)
    return users


def _result_tuple(r) -> tuple[int, int, int, int, int]:
    return (r.tenants, r.importance_changed, r.promoted, r.clustered, r.forgotten)


def test_parallel_cycle_matches_sequential_results() -> None:
    """Same data, run at concurrency 1 and 3 — identical aggregate result."""
    async def run_at(concurrency: int):
        engine = await make_engine()
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        dispatcher = InProcessEventDispatcher()
        await _seed_tenants(uowf, 4, engine)
        job = MemoryIntelligenceMaintenanceJob(
            uowf, graph, dispatcher, max_concurrency=concurrency,
        )
        result = await job.run_cycle()
        # Count promoted semantic memories actually persisted, across all tenants.
        async with uowf() as uow:
            everything = await uow.memories.list_for_analytics(None)
        semantic = sum(1 for m in everything if m.category is MemoryCategory.SEMANTIC)
        await engine.dispose()
        return _result_tuple(result), semantic

    seq_result, seq_semantic = _run(lambda: run_at(1))
    par_result, par_semantic = _run(lambda: run_at(3))

    assert seq_result == par_result
    assert seq_semantic == par_semantic
    assert seq_result[0] == 4          # four tenants
    assert seq_result[2] >= 4          # at least one promotion per tenant

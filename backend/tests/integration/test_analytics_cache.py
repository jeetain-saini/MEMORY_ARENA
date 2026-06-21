"""Integration tests for analytics cache-aside + invalidation (Stage 14 Phase 5).

SQLite + in-memory cache/metrics, single-event-loop pattern. Proves the cache is
read (hit/miss metrics), that it actually caches (a write the handler hasn't seen
yields a stale read), and that the invalidation handler clears it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.services.cache.cache_invalidation_handler import (
    CacheInvalidationEventHandler,
)
from app.application.services.memory_analytics_service import MemoryAnalyticsService
from app.application.services.observability.frozen_clock import FrozenClock
from app.domain.entities.memory import Memory
from app.domain.events.memory_events import MemoryCreated
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.cache.in_memory_cache import InMemoryCacheProvider
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.observability.in_memory_metrics import InMemoryMetricsSink
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _save(factory, user, content: str) -> None:
    memory = Memory.create(user_id=user, content=content, memory_type=MemoryType.FACT)
    async with SQLAlchemyUnitOfWork(factory) as uow:
        await uow.memories.save(memory)
        await uow.commit()


def _service(factory, cache, metrics) -> MemoryAnalyticsService:
    return MemoryAnalyticsService(
        SQLAlchemyUnitOfWork(factory), cache=cache, metrics=metrics, cache_ttl_seconds=60
    )


def test_cache_hit_miss_and_invalidation() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        factory = create_session_factory(engine)
        cache = InMemoryCacheProvider(FrozenClock(epoch=1000.0))
        metrics = InMemoryMetricsSink()
        svc = _service(factory, cache, metrics)
        handler = CacheInvalidationEventHandler(cache)

        await _save(factory, user, "first")
        a1 = await svc.get_analytics(user)          # miss -> compute -> cache
        a2 = await svc.get_analytics(user)          # hit
        assert a1 == a2 and a1.total_memories == 1

        await _save(factory, user, "second")        # DB now has 2...
        stale = await svc.get_analytics(user)       # ...but still served from cache
        assert stale.total_memories == 1            # proves the value was cached

        await handler.on_memory_mutation(
            MemoryCreated(memory_id=uuid4(), user_id=user, memory_type=MemoryType.FACT)
        )
        fresh = await svc.get_analytics(user)        # cache cleared -> recompute
        assert fresh.total_memories == 2

        counters = metrics.snapshot().counters
        assert counters["cache.hit.analytics"] == 2   # a2 + the stale read
        assert counters["cache.miss.analytics"] == 2  # a1 (cold) + fresh (post-invalidation)

    _run(scenario)


def test_cross_user_cache_isolation() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        a = await seed_user(engine)
        b = await seed_user(engine)
        factory = create_session_factory(engine)
        cache = InMemoryCacheProvider(FrozenClock(epoch=1000.0))
        metrics = InMemoryMetricsSink()
        svc = _service(factory, cache, metrics)

        await _save(factory, a, "a-mem")
        ra = await svc.get_analytics(a)
        rb = await svc.get_analytics(b)   # different key -> own (empty) data, not a's cache
        assert ra.total_memories == 1
        assert rb.total_memories == 0
        # global variant is a third, independent key.
        rg = await svc.get_analytics(None)
        assert rg.total_memories == 1  # all users
        assert metrics.snapshot().counters["cache.miss.analytics"] == 3

    _run(scenario)

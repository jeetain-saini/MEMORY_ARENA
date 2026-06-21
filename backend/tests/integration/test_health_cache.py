"""Integration tests for memory-health cache-aside (Stage 14 Phase 5)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TypeVar

from app.application.services.observability.frozen_clock import FrozenClock
from app.application.services.observability.memory_health_service import MemoryHealthService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.cache.in_memory_cache import InMemoryCacheProvider
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.observability.in_memory_metrics import InMemoryMetricsSink
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _save(factory, user, content: str) -> None:
    memory = Memory.create(user_id=user, content=content, memory_type=MemoryType.PROJECT)
    async with SQLAlchemyUnitOfWork(factory) as uow:
        await uow.memories.save(memory)
        await uow.commit()


def _service(factory, cache, metrics) -> MemoryHealthService:
    return MemoryHealthService(
        SQLAlchemyUnitOfWork(factory), InMemoryGraphRepository(),
        cache=cache, metrics=metrics, cache_ttl_seconds=60,
    )


def test_health_cache_hit_miss() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        factory = create_session_factory(engine)
        cache = InMemoryCacheProvider(FrozenClock(epoch=1000.0))
        metrics = InMemoryMetricsSink()
        svc = _service(factory, cache, metrics)

        await _save(factory, user, "ship it")
        h1 = await svc.get_health(user)   # miss -> compute -> cache
        h2 = await svc.get_health(user)   # hit
        assert h1 == h2
        counters = metrics.snapshot().counters
        assert counters["cache.miss.health"] == 1
        assert counters["cache.hit.health"] == 1

    _run(scenario)


def test_health_now_override_bypasses_cache() -> None:
    # A caller-supplied ``now`` is a deterministic override and must not read or
    # write the cache (otherwise a fixed-time call would poison the live value).
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        factory = create_session_factory(engine)
        cache = InMemoryCacheProvider(FrozenClock(epoch=1000.0))
        metrics = InMemoryMetricsSink()
        svc = _service(factory, cache, metrics)

        fixed = datetime(2026, 6, 21, tzinfo=timezone.utc)
        await svc.get_health(user, now=fixed)
        await svc.get_health(user, now=fixed)
        # No cache metrics recorded on the override path.
        assert metrics.snapshot().counters == {}

    _run(scenario)

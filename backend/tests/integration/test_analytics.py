"""Integration tests for MemoryAnalyticsService."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.services.memory_analytics_service import MemoryAnalyticsService
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def _high() -> MemoryScore:
    return MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1)


def test_analytics_empty_dataset() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        service = MemoryAnalyticsService(SQLAlchemyUnitOfWork(create_session_factory(engine)))
        result = await service.get_analytics(user_id)
        assert result.total_memories == 0
        assert result.average_score == 0.0
        assert sum(result.score_distribution.values()) == 0
        await engine.dispose()

    _run(scenario)


def test_analytics_counts_and_distribution() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        factory = create_session_factory(engine)
        uow = SQLAlchemyUnitOfWork(factory)

        m_active = Memory.create(user_id=user_id, content="a", memory_type=MemoryType.FACT)
        m_low = Memory(
            user_id=user_id, content="b", memory_type=MemoryType.FACT,
            score=MemoryScore(importance=0, utility=0, frequency=0, recency=0, confidence=0),
        )
        m_promoted = Memory(user_id=user_id, content="c", memory_type=MemoryType.GOAL, score=_high())
        m_promoted.promote()
        m_archived = Memory.create(user_id=user_id, content="d", memory_type=MemoryType.FACT)
        m_archived.archive()

        async with uow:
            for m in (m_active, m_low, m_promoted, m_archived):
                await uow.memories.save(m)
            await uow.commit()

        service = MemoryAnalyticsService(uow)
        result = await service.get_analytics(user_id)

        assert result.total_memories == 4
        assert result.active_memories == 3  # active, low, promoted (promotion keeps ACTIVE)
        assert result.archived_memories == 1
        assert result.promoted_memories == 1
        assert sum(result.score_distribution.values()) == 4
        assert 0.0 <= result.average_score <= 1.0
        await engine.dispose()

    _run(scenario)


def test_analytics_scopes_to_user() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_a = await seed_user(engine)
        user_b = await seed_user(engine)
        factory = create_session_factory(engine)
        uow = SQLAlchemyUnitOfWork(factory)

        async with uow:
            await uow.memories.save(Memory.create(user_id=user_a, content="a", memory_type=MemoryType.FACT))
            await uow.memories.save(Memory.create(user_id=user_b, content="b", memory_type=MemoryType.FACT))
            await uow.memories.save(Memory.create(user_id=user_b, content="c", memory_type=MemoryType.FACT))
            await uow.commit()

        service = MemoryAnalyticsService(uow)
        assert (await service.get_analytics(user_a)).total_memories == 1
        assert (await service.get_analytics(user_b)).total_memories == 2
        assert (await service.get_analytics(None)).total_memories == 3
        await engine.dispose()

    _run(scenario)

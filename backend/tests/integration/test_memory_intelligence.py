"""Integration tests for the Memory Intelligence Engine (SQLite + real dispatcher)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import UUID, uuid4

import pytest

from app.application.exceptions import MemoryNotFoundException, MemoryValidationException
from app.application.services.decay_strategies import ExponentialDecayStrategy
from app.application.services.intelligence_config import IntelligenceConfig
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.events.memory_events import (
    DomainEvent,
    MemoryArchived,
    MemoryDecayed,
    MemoryPromoted,
    MemoryReinforced,
)
from app.domain.exceptions.errors import InvalidMemoryStateError
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.database.session import create_session_factory
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")
NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _ctx():
    engine = await make_engine()
    user_id = await seed_user(engine)
    factory = create_session_factory(engine)
    uow = SQLAlchemyUnitOfWork(factory)
    dispatcher = InProcessEventDispatcher()
    captured: list[DomainEvent] = []
    dispatcher.register(DomainEvent, captured.append)
    return engine, uow, dispatcher, captured, user_id


async def _save(uow: SQLAlchemyUnitOfWork, memory: Memory) -> None:
    async with uow:
        await uow.memories.save(memory)
        await uow.commit()


def test_reinforce_increases_score_and_emits_event() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, captured, user_id = await _ctx()
        memory = Memory.create(user_id=user_id, content="reuse me", memory_type=MemoryType.SKILL)
        await _save(uow, memory)

        service = MemoryIntelligenceService(uow, dispatcher)
        resp = await service.reinforce_memory(memory.id, user_id=user_id, step=0.2)

        assert resp.total_score >= memory.total_score
        assert any(isinstance(e, MemoryReinforced) for e in captured)

        async with uow:
            stored = await uow.memories.get_by_id(memory.id)
        assert stored is not None and stored.score.frequency == pytest.approx(0.2)
        await engine.dispose()

    _run(scenario)


def test_reinforce_missing_raises_not_found() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, _captured, user_id = await _ctx()
        service = MemoryIntelligenceService(uow, dispatcher)
        with pytest.raises(MemoryNotFoundException):
            await service.reinforce_memory(uuid4(), user_id=user_id)
        await engine.dispose()

    _run(scenario)


def test_promote_high_score_sets_flag_and_priority() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, captured, user_id = await _ctx()
        memory = Memory(
            user_id=user_id, content="important", memory_type=MemoryType.GOAL,
            score=MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1),
        )
        await _save(uow, memory)

        service = MemoryIntelligenceService(uow, dispatcher)
        resp = await service.promote_memory(memory.id, user_id=user_id)
        assert resp.is_promoted is True
        assert resp.priority == 1
        assert resp.status is MemoryStatus.ACTIVE
        assert any(isinstance(e, MemoryPromoted) for e in captured)
        await engine.dispose()

    _run(scenario)


def test_promote_below_threshold_raises() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, _captured, user_id = await _ctx()
        memory = Memory.create(user_id=user_id, content="meh", memory_type=MemoryType.FACT)
        await _save(uow, memory)
        service = MemoryIntelligenceService(uow, dispatcher)
        with pytest.raises(InvalidMemoryStateError):
            await service.promote_memory(memory.id, user_id=user_id)
        await engine.dispose()

    _run(scenario)


def test_decay_reduces_recency() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, captured, user_id = await _ctx()
        memory = Memory(
            user_id=user_id, content="old", memory_type=MemoryType.FACT,
            score=MemoryScore(recency=1.0), updated_at=NOW - timedelta(days=7),
        )
        await _save(uow, memory)

        service = MemoryIntelligenceService(
            uow, dispatcher, decay_strategy=ExponentialDecayStrategy(half_life_days=7)
        )
        await service.decay_memory(memory.id, now=NOW)
        assert any(isinstance(e, MemoryDecayed) for e in captured)

        async with uow:
            stored = await uow.memories.get_by_id(memory.id)
        assert stored is not None and stored.score.recency == pytest.approx(0.5)
        await engine.dispose()

    _run(scenario)


def test_archive_eligible_memory() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, captured, user_id = await _ctx()
        memory = Memory(
            user_id=user_id, content="forgotten", memory_type=MemoryType.FACT,
            score=MemoryScore(importance=0, utility=0, frequency=0, recency=0, confidence=0),
            updated_at=NOW - timedelta(days=40),
        )
        await _save(uow, memory)

        service = MemoryIntelligenceService(uow, dispatcher)
        resp = await service.archive_memory(memory.id, user_id=user_id, now=NOW)
        assert resp.status is MemoryStatus.ARCHIVED
        assert any(isinstance(e, MemoryArchived) for e in captured)
        await engine.dispose()

    _run(scenario)


def test_archive_not_eligible_raises() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, _captured, user_id = await _ctx()
        memory = Memory.create(user_id=user_id, content="fresh", memory_type=MemoryType.FACT)
        await _save(uow, memory)
        service = MemoryIntelligenceService(uow, dispatcher)
        with pytest.raises(MemoryValidationException):
            await service.archive_memory(memory.id, user_id=user_id, now=NOW)
        await engine.dispose()

    _run(scenario)


def test_archive_force_overrides_criteria() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, _captured, user_id = await _ctx()
        memory = Memory.create(user_id=user_id, content="fresh", memory_type=MemoryType.FACT)
        await _save(uow, memory)
        service = MemoryIntelligenceService(uow, dispatcher)
        resp = await service.archive_memory(memory.id, user_id=user_id, force=True, now=NOW)
        assert resp.status is MemoryStatus.ARCHIVED
        await engine.dispose()

    _run(scenario)


def test_evaluate_memory_reports_standing() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, _captured, user_id = await _ctx()
        memory = Memory(
            user_id=user_id, content="strong", memory_type=MemoryType.FACT,
            score=MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1),
        )
        await _save(uow, memory)
        service = MemoryIntelligenceService(uow, dispatcher)
        evaluation = await service.evaluate_memory(memory.id, now=NOW)
        assert evaluation.total_score == pytest.approx(1.0)
        assert evaluation.is_promotable is True
        assert evaluation.should_archive is False
        await engine.dispose()

    _run(scenario)

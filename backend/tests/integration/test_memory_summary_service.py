"""Integration tests for MemorySummaryService (SQLite + deterministic generator)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.application.services.maintenance.memory_summary_service import MemorySummaryService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.summaries.deterministic_summary_generator import (
    DeterministicSummaryGenerator,
)
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _ctx():
    engine = await make_engine()
    user = await seed_user(engine)
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    service = MemorySummaryService(uow_factory, DeterministicSummaryGenerator())
    return engine, uow_factory, user, service


async def _save(uow_factory, user: UUID, content: str, mtype: MemoryType) -> Memory:
    memory = Memory.create(user_id=user, content=content, memory_type=mtype)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


def test_refresh_creates_summary_per_scope() -> None:
    async def scenario() -> None:
        engine, uow_factory, user, service = await _ctx()
        await _save(uow_factory, user, "ship the analytics platform", MemoryType.PROJECT)
        await _save(uow_factory, user, "learn rust this quarter", MemoryType.GOAL)

        result = await service.refresh(user)
        assert result.created == 2  # PROJECT + GOAL (no EXPERIENCE memories)

        async with uow_factory() as uow:
            project = await uow.summaries.get(user, MemoryType.PROJECT)
            goal = await uow.summaries.get(user, MemoryType.GOAL)
            experience = await uow.summaries.get(user, MemoryType.EXPERIENCE)
        assert project is not None and "analytics platform" in project.summary_text
        assert goal is not None and "rust" in goal.summary_text
        assert experience is None  # no source memories → no summary
        await engine.dispose()

    _run(scenario)


def test_refresh_is_idempotent_when_unchanged() -> None:
    async def scenario() -> None:
        engine, uow_factory, user, service = await _ctx()
        await _save(uow_factory, user, "ship the dashboard", MemoryType.PROJECT)

        first = await service.refresh(user)
        second = await service.refresh(user)
        assert first.created == 1
        assert second.created == 0 and second.unchanged == 1

        async with uow_factory() as uow:
            summary = await uow.summaries.get(user, MemoryType.PROJECT)
        assert summary is not None and summary.version == 1  # no version churn
        await engine.dispose()

    _run(scenario)


def test_refresh_bumps_version_on_change() -> None:
    async def scenario() -> None:
        engine, uow_factory, user, service = await _ctx()
        await _save(uow_factory, user, "ship the dashboard", MemoryType.PROJECT)
        await service.refresh(user)
        # Add a new project memory → summary text changes on next refresh.
        await _save(uow_factory, user, "build the reporting module", MemoryType.PROJECT)
        second = await service.refresh(user)
        assert second.updated == 1

        async with uow_factory() as uow:
            summary = await uow.summaries.get(user, MemoryType.PROJECT)
        assert summary is not None and summary.version == 2
        assert summary.source_count == 2
        await engine.dispose()

    _run(scenario)


def test_summaries_do_not_modify_source_memories() -> None:
    async def scenario() -> None:
        engine, uow_factory, user, service = await _ctx()
        memory = await _save(uow_factory, user, "ship the dashboard", MemoryType.PROJECT)
        await service.refresh(user)
        async with uow_factory() as uow:
            stored = await uow.memories.get_by_id(memory.id)
        assert stored is not None
        assert stored.content == "ship the dashboard"  # untouched
        assert stored.version == 1
        await engine.dispose()

    _run(scenario)


def test_refresh_empty_tenant_creates_nothing() -> None:
    async def scenario() -> None:
        engine, uow_factory, user, service = await _ctx()
        result = await service.refresh(user)
        assert result.created == 0 and result.updated == 0
        await engine.dispose()

    _run(scenario)


def test_refresh_provenance_tracks_source_ids() -> None:
    async def scenario() -> None:
        engine, uow_factory, user, service = await _ctx()
        memory = await _save(uow_factory, user, "ship the dashboard", MemoryType.PROJECT)
        await service.refresh(user)
        async with uow_factory() as uow:
            summary = await uow.summaries.get(user, MemoryType.PROJECT)
        assert summary is not None
        assert memory.id in summary.source_memory_ids
        await engine.dispose()

    _run(scenario)

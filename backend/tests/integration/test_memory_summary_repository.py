"""Integration tests for MemorySummaryRepositoryImpl (SQLite)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.domain.entities.memory_summary import MemorySummary
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _ctx():
    engine = await make_engine()
    user = await seed_user(engine)
    factory = create_session_factory(engine)
    return engine, SQLAlchemyUnitOfWork(factory), user


def test_upsert_inserts_then_reads() -> None:
    async def scenario() -> None:
        engine, uow, user = await _ctx()
        summary = MemorySummary.create(
            user_id=user, scope=MemoryType.GOAL, summary_text="goals", source_memory_ids=[uuid4()]
        )
        async with uow:
            await uow.summaries.upsert(summary)
            await uow.commit()
        async with uow:
            stored = await uow.summaries.get(user, MemoryType.GOAL)
        assert stored is not None
        assert stored.summary_text == "goals"
        assert stored.source_count == 1
        await engine.dispose()

    _run(scenario)


def test_upsert_updates_existing_row() -> None:
    async def scenario() -> None:
        engine, uow, user = await _ctx()
        ids = [uuid4()]
        summary = MemorySummary.create(
            user_id=user, scope=MemoryType.GOAL, summary_text="v1", source_memory_ids=ids
        )
        async with uow:
            await uow.summaries.upsert(summary)
            await uow.commit()
        summary.revise(summary_text="v2", source_memory_ids=ids)
        async with uow:
            await uow.summaries.upsert(summary)
            await uow.commit()
        async with uow:
            stored = await uow.summaries.get(user, MemoryType.GOAL)
            all_for_user = await uow.summaries.list_for_user(user)
        assert stored is not None and stored.summary_text == "v2" and stored.version == 2
        assert len(all_for_user) == 1  # upsert, not insert
        await engine.dispose()

    _run(scenario)


def test_list_for_user_returns_all_scopes() -> None:
    async def scenario() -> None:
        engine, uow, user = await _ctx()
        async with uow:
            for scope in (MemoryType.GOAL, MemoryType.PROJECT):
                await uow.summaries.upsert(
                    MemorySummary.create(
                        user_id=user, scope=scope, summary_text=scope.value, source_memory_ids=[]
                    )
                )
            await uow.commit()
        async with uow:
            summaries = await uow.summaries.list_for_user(user)
        assert {s.scope for s in summaries} == {MemoryType.GOAL, MemoryType.PROJECT}
        await engine.dispose()

    _run(scenario)


def test_delete_removes_summary() -> None:
    async def scenario() -> None:
        engine, uow, user = await _ctx()
        async with uow:
            await uow.summaries.upsert(
                MemorySummary.create(
                    user_id=user, scope=MemoryType.GOAL, summary_text="x", source_memory_ids=[]
                )
            )
            await uow.commit()
        async with uow:
            await uow.summaries.delete(user, MemoryType.GOAL)
            await uow.commit()
        async with uow:
            assert await uow.summaries.get(user, MemoryType.GOAL) is None
        await engine.dispose()

    _run(scenario)

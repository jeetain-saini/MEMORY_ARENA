"""Use-case tests against an isolated SQLite DB and a real event dispatcher.

Exercises the full application path: use case -> Unit of Work -> repository ->
DB, plus domain-event dispatch. Coroutines are driven with ``asyncio.run`` so no
pytest-asyncio plugin is required.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.application.dto.memory_dto import (
    CreateMemoryRequest,
    MemorySearchRequest,
    UpdateMemoryRequest,
)
from app.application.exceptions import MemoryNotFoundException
from app.application.use_cases.memory_use_cases_impl import (
    CreateMemoryUseCaseImpl,
    DeleteMemoryUseCaseImpl,
    SearchMemoryUseCaseImpl,
    UpdateMemoryUseCaseImpl,
)
from app.domain.events.memory_events import (
    DomainEvent,
    MemoryCreated,
    MemoryDeleted,
    MemoryUpdated,
)
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.base import Base
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _setup() -> tuple[AsyncEngine, SQLAlchemyUnitOfWork, InProcessEventDispatcher, list, UUID]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = create_session_factory(engine)
    user_id = uuid4()
    async with factory() as session:
        session.add(UserModel(id=user_id, email=f"{user_id}@example.com"))
        await session.commit()

    uow = SQLAlchemyUnitOfWork(factory)
    dispatcher = InProcessEventDispatcher()
    captured: list[DomainEvent] = []
    dispatcher.register(DomainEvent, captured.append)
    return engine, uow, dispatcher, captured, user_id


def test_create_persists_and_emits_event() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, captured, user_id = await _setup()
        uc = CreateMemoryUseCaseImpl(uow, dispatcher)

        response = await uc.execute(
            CreateMemoryRequest(user_id=user_id, content="hello", memory_type=MemoryType.FACT)
        )
        assert response.content == "hello"
        assert any(isinstance(e, MemoryCreated) for e in captured)

        async with uow:
            stored = await uow.memories.get_by_id(response.id)
        assert stored is not None
        await engine.dispose()

    _run(scenario)


def test_update_snapshots_version_and_emits_event() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, captured, user_id = await _setup()
        create = CreateMemoryUseCaseImpl(uow, dispatcher)
        update = UpdateMemoryUseCaseImpl(uow, dispatcher)

        created = await create.execute(
            CreateMemoryRequest(user_id=user_id, content="v1", memory_type=MemoryType.FACT)
        )
        captured.clear()
        updated = await update.execute(
            UpdateMemoryRequest(memory_id=created.id, user_id=user_id, content="v2", reason="fix")
        )
        assert updated.content == "v2"
        assert updated.version == 2
        assert any(isinstance(e, MemoryUpdated) for e in captured)

        async with uow:
            versions = await uow.versions.list_for_memory(created.id)
        assert len(versions) == 1  # pre-edit snapshot
        assert versions[0].content == "v1"
        await engine.dispose()

    _run(scenario)


def test_update_missing_raises_not_found() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, _captured, user_id = await _setup()
        update = UpdateMemoryUseCaseImpl(uow, dispatcher)
        with pytest.raises(MemoryNotFoundException):
            await update.execute(
                UpdateMemoryRequest(memory_id=uuid4(), user_id=user_id, content="x")
            )
        await engine.dispose()

    _run(scenario)


def test_delete_soft_deletes_and_emits_event() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, captured, user_id = await _setup()
        create = CreateMemoryUseCaseImpl(uow, dispatcher)
        delete = DeleteMemoryUseCaseImpl(uow, dispatcher)

        created = await create.execute(
            CreateMemoryRequest(user_id=user_id, content="bye", memory_type=MemoryType.FACT)
        )
        captured.clear()
        await delete.execute(memory_id=created.id, user_id=user_id)
        assert any(isinstance(e, MemoryDeleted) for e in captured)

        async with uow:
            assert await uow.memories.get_by_id(created.id) is None
        await engine.dispose()

    _run(scenario)


def test_search_returns_matches() -> None:
    async def scenario() -> None:
        engine, uow, dispatcher, _captured, user_id = await _setup()
        create = CreateMemoryUseCaseImpl(uow, dispatcher)
        search = SearchMemoryUseCaseImpl(uow)

        await create.execute(
            CreateMemoryRequest(user_id=user_id, content="Paris is in France", memory_type=MemoryType.FACT)
        )
        await create.execute(
            CreateMemoryRequest(user_id=user_id, content="Finish report", memory_type=MemoryType.GOAL)
        )
        results = await search.execute(
            MemorySearchRequest(user_id=user_id, memory_types=[MemoryType.GOAL])
        )
        assert len(results) == 1 and results[0].content == "Finish report"
        await engine.dispose()

    _run(scenario)

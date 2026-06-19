"""Integration tests for EmbeddingService (SQLite + deterministic provider)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.interfaces.embedding_job_processor import EmbeddingAction, EmbeddingJob
from app.application.services.embedding_service import EmbeddingService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.embeddings.deterministic_provider import DeterministicEmbeddingProvider
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")
DIMS = 16


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _ctx():
    engine = await make_engine()
    user_id = await seed_user(engine)
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    service = EmbeddingService(uow_factory, DeterministicEmbeddingProvider(dimensions=DIMS))
    return engine, factory, uow_factory, service, user_id


async def _save_memory(uow_factory, user_id, content="hello world") -> Memory:
    memory = Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


def test_generate_embedding_returns_vector() -> None:
    async def scenario() -> None:
        engine, _f, _uf, service, user_id = await _ctx()
        memory = Memory.create(user_id=user_id, content="text", memory_type=MemoryType.FACT)
        vector = await service.generate_embedding(memory)
        assert len(vector) == DIMS
        await engine.dispose()

    _run(scenario)


def test_store_embedding_persists() -> None:
    async def scenario() -> None:
        engine, _f, uow_factory, service, user_id = await _ctx()
        memory = await _save_memory(uow_factory, user_id)
        record = await service.store_embedding(memory)
        assert record.dimensions == DIMS

        async with uow_factory() as uow:
            fetched = await uow.embeddings.get_embedding(memory.id)
        assert fetched is not None and len(fetched.vector) == DIMS
        await engine.dispose()

    _run(scenario)


def test_update_embedding_changes_vector() -> None:
    async def scenario() -> None:
        engine, _f, uow_factory, service, user_id = await _ctx()
        memory = await _save_memory(uow_factory, user_id, content="v1")
        await service.store_embedding(memory)

        async with uow_factory() as uow:
            first = await uow.embeddings.get_embedding(memory.id)

        memory.update_content("a totally different content")
        await service.update_embedding(memory)

        async with uow_factory() as uow:
            second = await uow.embeddings.get_embedding(memory.id)
        assert first is not None and second is not None
        assert first.vector != second.vector
        await engine.dispose()

    _run(scenario)


def test_delete_embedding_removes_it() -> None:
    async def scenario() -> None:
        engine, _f, uow_factory, service, user_id = await _ctx()
        memory = await _save_memory(uow_factory, user_id)
        await service.store_embedding(memory)
        await service.delete_embedding(memory)

        async with uow_factory() as uow:
            assert await uow.embeddings.get_embedding(memory.id) is None
        await engine.dispose()

    _run(scenario)


def test_process_upsert_and_delete_jobs() -> None:
    async def scenario() -> None:
        engine, _f, uow_factory, service, user_id = await _ctx()
        memory = await _save_memory(uow_factory, user_id)

        await service.process(EmbeddingJob(EmbeddingAction.UPSERT, memory.id))
        async with uow_factory() as uow:
            assert await uow.embeddings.get_embedding(memory.id) is not None

        await service.process(EmbeddingJob(EmbeddingAction.DELETE, memory.id))
        async with uow_factory() as uow:
            assert await uow.embeddings.get_embedding(memory.id) is None
        await engine.dispose()

    _run(scenario)


def test_process_upsert_missing_memory_is_noop() -> None:
    async def scenario() -> None:
        engine, _f, uow_factory, service, _user_id = await _ctx()
        # No memory with this id -> should silently do nothing.
        await service.process(EmbeddingJob(EmbeddingAction.UPSERT, uuid4()))
        await engine.dispose()

    _run(scenario)

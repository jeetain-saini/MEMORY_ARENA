"""Integration tests for MemoryEmbeddingRepositoryImpl (SQLite)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.dto.embedding_dto import EmbeddingRecord
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _seed_memory(uow: SQLAlchemyUnitOfWork, user_id) -> Memory:
    memory = Memory.create(user_id=user_id, content="content", memory_type=MemoryType.FACT)
    async with uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


def _record(memory_id, vector, model="m1") -> EmbeddingRecord:
    return EmbeddingRecord(
        memory_id=memory_id, vector=vector, model_name=model, dimensions=len(vector)
    )


def test_save_and_get_embedding() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        memory = await _seed_memory(uow, user_id)

        async with uow:
            await uow.embeddings.save_embedding(_record(memory.id, [0.1, 0.2, 0.3]))
            await uow.commit()

        async with uow:
            fetched = await uow.embeddings.get_embedding(memory.id)
        assert fetched is not None
        assert fetched.vector == [0.1, 0.2, 0.3]
        assert fetched.dimensions == 3
        assert fetched.model_name == "m1"
        await engine.dispose()

    _run(scenario)


def test_save_is_upsert() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        memory = await _seed_memory(uow, user_id)

        async with uow:
            await uow.embeddings.save_embedding(_record(memory.id, [0.1, 0.1]))
            await uow.commit()
        async with uow:
            await uow.embeddings.save_embedding(_record(memory.id, [0.9, 0.9]))
            await uow.commit()

        async with uow:
            fetched = await uow.embeddings.get_embedding(memory.id, model_name="m1")
        assert fetched is not None and fetched.vector == [0.9, 0.9]
        await engine.dispose()

    _run(scenario)


def test_update_embedding() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        memory = await _seed_memory(uow, user_id)

        async with uow:
            await uow.embeddings.save_embedding(_record(memory.id, [0.0, 0.0]))
            await uow.commit()
        async with uow:
            await uow.embeddings.update_embedding(_record(memory.id, [0.5, 0.6]))
            await uow.commit()

        async with uow:
            fetched = await uow.embeddings.get_embedding(memory.id)
        assert fetched is not None and fetched.vector == [0.5, 0.6]
        await engine.dispose()

    _run(scenario)


def test_delete_embedding() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        memory = await _seed_memory(uow, user_id)

        async with uow:
            await uow.embeddings.save_embedding(_record(memory.id, [0.1, 0.2]))
            await uow.commit()
        async with uow:
            await uow.embeddings.delete_embedding(memory.id)
            await uow.commit()

        async with uow:
            assert await uow.embeddings.get_embedding(memory.id) is None
        await engine.dispose()

    _run(scenario)


def test_get_missing_returns_none() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        async with uow:
            assert await uow.embeddings.get_embedding(uuid4()) is None
        await engine.dispose()

    _run(scenario)

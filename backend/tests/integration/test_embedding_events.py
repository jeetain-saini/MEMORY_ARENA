"""Event-driven embedding integration: memory events -> embeddings.

Wires the full pipeline (dispatcher -> handler -> processor -> service -> repo)
against SQLite and asserts that lifecycle events drive embedding storage.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.services.embedding_event_handler import EmbeddingEventHandler
from app.application.services.embedding_service import EmbeddingService
from app.domain.entities.memory import Memory
from app.domain.events.memory_events import MemoryCreated, MemoryDeleted, MemoryUpdated
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.embeddings.deterministic_provider import DeterministicEmbeddingProvider
from app.infrastructure.embeddings.in_process_processor import InProcessEmbeddingJobProcessor
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _wire():
    engine = await make_engine()
    user_id = await seed_user(engine)
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    service = EmbeddingService(uow_factory, DeterministicEmbeddingProvider(dimensions=8))
    processor = InProcessEmbeddingJobProcessor(service.process)
    dispatcher = InProcessEventDispatcher()
    EmbeddingEventHandler(processor).register(dispatcher)
    return engine, uow_factory, processor, dispatcher, user_id


async def _persist_memory(uow_factory, user_id, content="remember") -> Memory:
    memory = Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


def test_memory_created_event_generates_embedding() -> None:
    async def scenario() -> None:
        engine, uow_factory, processor, dispatcher, user_id = await _wire()
        memory = await _persist_memory(uow_factory, user_id)

        await dispatcher.dispatch(
            [MemoryCreated(memory_id=memory.id, user_id=user_id, memory_type=memory.memory_type)]
        )
        await processor.drain()

        async with uow_factory() as uow:
            assert await uow.embeddings.get_embedding(memory.id) is not None
        await engine.dispose()

    _run(scenario)


def test_memory_updated_event_refreshes_embedding() -> None:
    async def scenario() -> None:
        engine, uow_factory, processor, dispatcher, user_id = await _wire()
        memory = await _persist_memory(uow_factory, user_id, content="v1")

        await dispatcher.dispatch(
            [MemoryUpdated(memory_id=memory.id, user_id=user_id, version=2)]
        )
        await processor.drain()

        async with uow_factory() as uow:
            assert await uow.embeddings.get_embedding(memory.id) is not None
        await engine.dispose()

    _run(scenario)


def test_memory_deleted_event_removes_embedding() -> None:
    async def scenario() -> None:
        engine, uow_factory, processor, dispatcher, user_id = await _wire()
        memory = await _persist_memory(uow_factory, user_id)

        # First create the embedding...
        await dispatcher.dispatch(
            [MemoryCreated(memory_id=memory.id, user_id=user_id, memory_type=memory.memory_type)]
        )
        await processor.drain()
        # ...then delete it.
        await dispatcher.dispatch([MemoryDeleted(memory_id=memory.id, user_id=user_id)])
        await processor.drain()

        async with uow_factory() as uow:
            assert await uow.embeddings.get_embedding(memory.id) is None
        await engine.dispose()

    _run(scenario)

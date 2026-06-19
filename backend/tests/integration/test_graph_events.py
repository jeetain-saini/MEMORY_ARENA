"""Integration: memory domain events -> graph-sync jobs.

Wires the full graph pipeline (dispatcher -> handler -> job processor ->
sync service -> in-memory graph) against SQLite and asserts that lifecycle
events drive graph node sync/removal off the request path.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.services.graph.config import GraphConfig
from app.application.services.graph.event_handler import GraphEventHandler
from app.application.services.graph.relationship_service import GraphRelationshipService
from app.application.services.graph.sync_service import GraphSyncService
from app.domain.entities.memory import Memory
from app.domain.events.memory_events import MemoryCreated, MemoryDeleted, MemoryUpdated
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.graph.in_process_processor import InProcessGraphJobProcessor
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

    config = GraphConfig()
    repo = InMemoryGraphRepository()
    sync = GraphSyncService(uow_factory, repo, GraphRelationshipService(config), config)
    processor = InProcessGraphJobProcessor(sync.process)
    dispatcher = InProcessEventDispatcher()
    GraphEventHandler(processor).register(dispatcher)
    return engine, uow_factory, repo, processor, dispatcher, user_id


async def _persist(uow_factory, user_id, content="python rocks") -> Memory:
    memory = Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


def test_created_event_syncs_node() -> None:
    async def scenario() -> None:
        engine, uow_factory, repo, processor, dispatcher, user_id = await _wire()
        memory = await _persist(uow_factory, user_id)

        await dispatcher.dispatch(
            [MemoryCreated(memory_id=memory.id, user_id=user_id, memory_type=memory.memory_type)]
        )
        await processor.drain()

        assert await repo.get_node(str(memory.id)) is not None
        await engine.dispose()

    _run(scenario)


def test_updated_event_resyncs_node() -> None:
    async def scenario() -> None:
        engine, uow_factory, repo, processor, dispatcher, user_id = await _wire()
        memory = await _persist(uow_factory, user_id, content="python v1")

        await dispatcher.dispatch([MemoryUpdated(memory_id=memory.id, user_id=user_id, version=2)])
        await processor.drain()

        node = await repo.get_node(str(memory.id))
        assert node is not None and node.properties["content"] == "python v1"
        await engine.dispose()

    _run(scenario)


def test_deleted_event_removes_node() -> None:
    async def scenario() -> None:
        engine, uow_factory, repo, processor, dispatcher, user_id = await _wire()
        memory = await _persist(uow_factory, user_id)

        await dispatcher.dispatch(
            [MemoryCreated(memory_id=memory.id, user_id=user_id, memory_type=memory.memory_type)]
        )
        await processor.drain()
        await dispatcher.dispatch([MemoryDeleted(memory_id=memory.id, user_id=user_id)])
        await processor.drain()

        assert await repo.get_node(str(memory.id)) is None
        await engine.dispose()

    _run(scenario)

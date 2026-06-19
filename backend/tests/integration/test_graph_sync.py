"""Integration: GraphSyncService against SQLite + in-memory graph backend.

Covers node upsert, edge (re-)derivation, stale-edge removal on update, node
removal on delete, and the bounded candidate scan (max_sync_candidates).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.services.graph.config import GraphConfig
from app.application.services.graph.relationship_service import GraphRelationshipService
from app.application.services.graph.sync_service import GraphSyncService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _wire(config: GraphConfig | None = None):
    engine = await make_engine()
    user_id = await seed_user(engine)
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    config = config or GraphConfig()
    repo = InMemoryGraphRepository()
    sync = GraphSyncService(uow_factory, repo, GraphRelationshipService(config), config)
    return engine, uow_factory, repo, sync, user_id


async def _persist(uow_factory, user_id, content: str) -> Memory:
    memory = Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


async def _update_content(uow_factory, memory: Memory, content: str) -> Memory:
    memory.update_content(content)
    async with uow_factory() as uow:
        await uow.memories.update(memory)
        await uow.commit()
    return memory


def test_sync_creates_node_and_edges() -> None:
    async def scenario() -> None:
        engine, uow_factory, repo, sync, user_id = await _wire()
        a = await _persist(uow_factory, user_id, "python programming rocks")
        b = await _persist(uow_factory, user_id, "python tooling rules")

        await sync.sync_memory(a.id)
        await sync.sync_memory(b.id)

        assert await repo.get_node(str(a.id)) is not None
        assert await repo.get_node(str(b.id)) is not None
        edges = await repo.get_edges(str(a.id))
        assert any(
            {e.source_id, e.target_id} == {str(a.id), str(b.id)} for e in edges
        )
        await engine.dispose()

    _run(scenario)


def test_update_removes_stale_edges() -> None:
    async def scenario() -> None:
        engine, uow_factory, repo, sync, user_id = await _wire()
        a = await _persist(uow_factory, user_id, "python programming rocks")
        b = await _persist(uow_factory, user_id, "python tooling rules")
        await sync.sync_memory(a.id)
        await sync.sync_memory(b.id)
        assert await repo.get_edges(str(a.id))  # edge exists via shared "python"

        # Change A so it shares nothing with B, then re-sync.
        await _update_content(uow_factory, a, "gardening outdoors weekend")
        await sync.sync_memory(a.id)

        assert await repo.get_edges(str(a.id)) == []  # stale edge pruned
        await engine.dispose()

    _run(scenario)


def test_delete_removes_node_and_incident_edges() -> None:
    async def scenario() -> None:
        engine, uow_factory, repo, sync, user_id = await _wire()
        a = await _persist(uow_factory, user_id, "python programming rocks")
        b = await _persist(uow_factory, user_id, "python tooling rules")
        await sync.sync_memory(a.id)
        await sync.sync_memory(b.id)

        await sync.remove_memory(a.id)

        assert await repo.get_node(str(a.id)) is None
        assert await repo.get_edges(str(b.id)) == []  # incident edge gone too
        await engine.dispose()

    _run(scenario)


def test_bounded_candidate_scan() -> None:
    async def scenario() -> None:
        engine, uow_factory, repo, sync, user_id = await _wire(
            GraphConfig(max_sync_candidates=1)
        )
        # Oldest first; all share "python".
        oldest = await _persist(uow_factory, user_id, "python one")
        await _persist(uow_factory, user_id, "python two")
        await _persist(uow_factory, user_id, "python three")  # newest

        await sync.sync_memory(oldest.id)

        # Only the single most-recent candidate is compared, so at most one edge.
        edges = await repo.get_edges(str(oldest.id))
        assert len(edges) == 1
        await engine.dispose()

    _run(scenario)


def test_sync_missing_memory_is_noop() -> None:
    async def scenario() -> None:
        from uuid import uuid4

        engine, uow_factory, repo, sync, _user_id = await _wire()
        missing = uuid4()

        # Syncing/removing a non-existent id must not raise or create a node.
        await sync.sync_memory(missing)
        await sync.remove_memory(missing)
        assert await repo.get_node(str(missing)) is None
        await engine.dispose()

    _run(scenario)

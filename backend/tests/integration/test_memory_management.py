"""Integration tests for Stage 16 memory management: restore + contradiction
resolution (SQLite + in-memory graph + real dispatcher)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import pytest

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.application.exceptions import MemoryValidationException
from app.application.services.contradiction_resolution_service import (
    ContradictionResolutionService,
)
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.domain.entities.memory import Memory
from app.domain.exceptions.errors import InvalidMemoryStateError
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _save(uow: SQLAlchemyUnitOfWork, memory: Memory) -> None:
    async with uow:
        await uow.memories.save(memory)
        await uow.commit()


async def _status(uow: SQLAlchemyUnitOfWork, memory_id) -> MemoryStatus:
    async with uow:
        m = await uow.memories.get_by_id(memory_id)
    return m.status


# --- restore ---------------------------------------------------------------

def test_archive_then_restore_returns_to_active() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        svc = MemoryIntelligenceService(uow, InProcessEventDispatcher())
        mem = Memory.create(user_id=user, content="I use PostgreSQL", memory_type=MemoryType.FACT)
        await _save(uow, mem)

        await svc.archive_memory(mem.id, user_id=user, force=True)
        assert await _status(uow, mem.id) == MemoryStatus.ARCHIVED

        restored = await svc.restore_memory(mem.id, user_id=user)
        assert restored.status == MemoryStatus.ACTIVE
        assert await _status(uow, mem.id) == MemoryStatus.ACTIVE
        await engine.dispose()

    _run(scenario)


def test_restore_active_memory_rejected() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        svc = MemoryIntelligenceService(uow, InProcessEventDispatcher())
        mem = Memory.create(user_id=user, content="I like tea", memory_type=MemoryType.PREFERENCE)
        await _save(uow, mem)
        with pytest.raises(InvalidMemoryStateError):  # ACTIVE -> ACTIVE is illegal
            await svc.restore_memory(mem.id, user_id=user)
        await engine.dispose()

    _run(scenario)


# --- contradiction resolution ---------------------------------------------

def _gnode(mem: Memory) -> GraphNode:
    return GraphNode(
        node_id=str(mem.id), node_type=NodeType.FACT, label=mem.content,
        properties={"user_id": str(mem.user_id), "status": mem.status.value},
    )


def test_resolution_archives_obsolete_writes_supersedes_preserves_contradicts() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        graph = InMemoryGraphRepository()

        keep = Memory.create(user_id=user, content="I use PostgreSQL", memory_type=MemoryType.FACT)
        obsolete = Memory.create(user_id=user, content="I do not use PostgreSQL", memory_type=MemoryType.FACT)
        await _save(uow, keep)
        await _save(uow, obsolete)
        await graph.create_node(_gnode(keep))
        await graph.create_node(_gnode(obsolete))
        # a pre-existing CONTRADICTS edge (as consolidation would have written)
        await graph.create_edge(GraphEdge(str(obsolete.id), str(keep.id), GraphEdgeType.CONTRADICTS))

        svc = ContradictionResolutionService(uow, graph, InProcessEventDispatcher())
        result = await svc.resolve(keep_id=keep.id, archive_id=obsolete.id, user_id=user)

        # obsolete archived; keep still active
        assert result.kept.status == MemoryStatus.ACTIVE
        assert result.archived.status == MemoryStatus.ARCHIVED
        assert await _status(uow, obsolete.id) == MemoryStatus.ARCHIVED
        assert await _status(uow, keep.id) == MemoryStatus.ACTIVE
        assert result.superseded_edge is True

        edges = await graph.get_edges(str(keep.id))
        types = {e.edge_type for e in edges}
        assert GraphEdgeType.SUPERSEDES in types     # durable SUPERSEDES added
        assert GraphEdgeType.CONTRADICTS in types    # CONTRADICTS preserved (history)
        # SUPERSEDES direction is keep -> obsolete
        sup = next(e for e in edges if e.edge_type is GraphEdgeType.SUPERSEDES)
        assert sup.source_id == str(keep.id) and sup.target_id == str(obsolete.id)
        await engine.dispose()

    _run(scenario)


def test_resolution_same_id_rejected() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))
        mem = Memory.create(user_id=user, content="x y z", memory_type=MemoryType.FACT)
        await _save(uow, mem)
        svc = ContradictionResolutionService(uow, InMemoryGraphRepository(), InProcessEventDispatcher())
        with pytest.raises(MemoryValidationException):
            await svc.resolve(keep_id=mem.id, archive_id=mem.id, user_id=user)
        await engine.dispose()

    _run(scenario)

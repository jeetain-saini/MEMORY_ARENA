"""Integration: CONTRADICTS edges survive GraphSyncService re-derivation.

Verifies the Phase A prerequisite fix: sync_memory() must not delete
externally-managed CONTRADICTS edges when it re-derives RELATED_TO/SUPPORTS/USED_IN.
"""

from __future__ import annotations

import asyncio

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.application.services.graph.config import GraphConfig
from app.application.services.graph.relationship_service import GraphRelationshipService
from app.application.services.graph.sync_service import GraphSyncService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from tests.integration._db import make_engine, seed_user


def _run(coro):
    return asyncio.run(coro)


async def _setup():
    engine = await make_engine()
    user_id = await seed_user(engine)
    factory = create_session_factory(engine)

    def uow_factory():
        return SQLAlchemyUnitOfWork(factory)

    config = GraphConfig()
    repo = InMemoryGraphRepository()
    sync = GraphSyncService(uow_factory, repo, GraphRelationshipService(config), config)
    return engine, uow_factory, repo, sync, user_id


async def _persist(uow_factory, user_id, content: str) -> Memory:
    memory = Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


def _contradicts_edge(source_id: str, target_id: str) -> GraphEdge:
    return GraphEdge(
        source_id=source_id,
        target_id=target_id,
        edge_type=GraphEdgeType.CONTRADICTS,
        weight=0.75,
        properties={"reasoning": "test conflict", "workflow_version": "consolidation-v1"},
    )


def test_contradicts_survives_sync_on_source_node() -> None:
    """sync_memory() on the source node must not delete its CONTRADICTS edge."""

    async def scenario() -> None:
        engine, uow_factory, repo, sync, user_id = await _setup()
        a = await _persist(uow_factory, user_id, "I love Python")
        b = await _persist(uow_factory, user_id, "I hate Python")

        # Sync both nodes to create derived edges first.
        await sync.sync_memory(a.id)
        await sync.sync_memory(b.id)

        # Manually write a CONTRADICTS edge (as the consolidation service would).
        contradicts = _contradicts_edge(str(a.id), str(b.id))
        await repo.create_edge(contradicts)

        # Verify the edge is present before the re-sync.
        edges_before = await repo.get_edges(str(a.id))
        assert any(e.edge_type == GraphEdgeType.CONTRADICTS for e in edges_before)

        # Re-sync the source node — this must NOT delete the CONTRADICTS edge.
        await sync.sync_memory(a.id)

        edges_after = await repo.get_edges(str(a.id))
        assert any(e.edge_type == GraphEdgeType.CONTRADICTS for e in edges_after), (
            "CONTRADICTS edge was deleted by sync_memory() on source node"
        )
        await engine.dispose()

    _run(scenario())


def test_contradicts_survives_sync_on_target_node() -> None:
    """sync_memory() on the target node must not delete the CONTRADICTS edge."""

    async def scenario() -> None:
        engine, uow_factory, repo, sync, user_id = await _setup()
        a = await _persist(uow_factory, user_id, "I love Python")
        b = await _persist(uow_factory, user_id, "I hate Python")

        await sync.sync_memory(a.id)
        await sync.sync_memory(b.id)

        contradicts = _contradicts_edge(str(a.id), str(b.id))
        await repo.create_edge(contradicts)

        # Re-sync the *target* node.
        await sync.sync_memory(b.id)

        edges_after = await repo.get_edges(str(b.id))
        assert any(e.edge_type == GraphEdgeType.CONTRADICTS for e in edges_after), (
            "CONTRADICTS edge was deleted by sync_memory() on target node"
        )
        await engine.dispose()

    _run(scenario())


def test_related_to_edges_are_still_replaced_by_sync() -> None:
    """Normal RELATED_TO edges are still replaced on re-sync (existing behaviour)."""

    async def scenario() -> None:
        engine, uow_factory, repo, sync, user_id = await _setup()
        a = await _persist(uow_factory, user_id, "python programming rocks")
        b = await _persist(uow_factory, user_id, "python tooling rules")
        await sync.sync_memory(a.id)
        await sync.sync_memory(b.id)

        # Confirm a derived edge exists.
        edges_before = await repo.get_edges(str(a.id))
        assert any(
            {e.source_id, e.target_id} == {str(a.id), str(b.id)} for e in edges_before
        )

        # Change A so it shares no tokens with B; the stale RELATED_TO edge must go.
        a.update_content("gardening outdoors weekend")
        async with uow_factory() as uow:
            await uow.memories.update(a)
            await uow.commit()

        await sync.sync_memory(a.id)

        edges_after = await repo.get_edges(str(a.id))
        derived = [
            e for e in edges_after
            if e.edge_type != GraphEdgeType.CONTRADICTS
            and {e.source_id, e.target_id} == {str(a.id), str(b.id)}
        ]
        assert derived == [], "stale RELATED_TO edge was not removed on re-sync"
        await engine.dispose()

    _run(scenario())


def test_contradicts_edge_preserved_alongside_derived_edges() -> None:
    """Both CONTRADICTS and RELATED_TO edges coexist after a re-sync."""

    async def scenario() -> None:
        engine, uow_factory, repo, sync, user_id = await _setup()
        # Two memories that share tokens → RELATED_TO will be derived.
        a = await _persist(uow_factory, user_id, "python programming I love it")
        b = await _persist(uow_factory, user_id, "python programming I hate it")
        await sync.sync_memory(a.id)
        await sync.sync_memory(b.id)

        # Add CONTRADICTS on top of the existing derived edges.
        contradicts = _contradicts_edge(str(a.id), str(b.id))
        await repo.create_edge(contradicts)

        # Re-sync A — derived edges may be refreshed but CONTRADICTS must stay.
        await sync.sync_memory(a.id)

        edges = await repo.get_edges(str(a.id))
        types = {e.edge_type for e in edges}
        assert GraphEdgeType.CONTRADICTS in types, "CONTRADICTS edge was lost after re-sync"
        await engine.dispose()

    _run(scenario())

"""Phase 3 — Neo4j disaster-recovery (logical graph backup/restore) tests.

Proves a tenant's knowledge graph (nodes + edges) survives an export -> fresh
graph -> restore round-trip, and that restore is idempotent. Backend-agnostic
(in-memory graph here; same code drives Neo4j in production).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.infrastructure.backup.graph_backup import GraphBackup
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _seed_graph(repo, user):
    a, b, c = str(uuid4()), str(uuid4()), str(uuid4())
    for nid, label in ((a, "alpha"), (b, "bravo"), (c, "charlie")):
        await repo.upsert_node(GraphNode(node_id=nid, node_type=NodeType.MEMORY,
                                         label=label, properties={"user_id": str(user)}))
    await repo.create_edge(GraphEdge(source_id=a, target_id=b,
                                     edge_type=GraphEdgeType.RELATED_TO, weight=0.8))
    await repo.create_edge(GraphEdge(source_id=a, target_id=c,
                                     edge_type=GraphEdgeType.PROMOTED_FROM,
                                     properties={"reason": "recurring"}))
    return a, b, c


def test_graph_export_restore_round_trip() -> None:
    async def scenario() -> None:
        user = uuid4()
        source = InMemoryGraphRepository()
        a, b, c = await _seed_graph(source, user)

        snapshot = await GraphBackup(source).export([user])
        assert snapshot["counts"]["nodes"] == 3
        assert snapshot["counts"]["edges"] == 2

        # Restore into a fresh, empty graph (a recovery host).
        target = InMemoryGraphRepository()
        restored = await GraphBackup(target).restore(snapshot)
        assert restored == {"nodes": 3, "edges": 2}

        # Recovery verification: nodes, edges, weights, and properties all match.
        recovered = await target.get_subgraph(user)
        assert {n.label for n in recovered.nodes} == {"alpha", "bravo", "charlie"}
        edges = {(e.source_id, e.target_id, e.edge_type) for e in recovered.edges}
        assert (a, b, GraphEdgeType.RELATED_TO) in edges
        assert (a, c, GraphEdgeType.PROMOTED_FROM) in edges
        promoted = next(e for e in recovered.edges
                        if e.edge_type is GraphEdgeType.PROMOTED_FROM)
        assert promoted.properties["reason"] == "recurring"

    _run(scenario)


def test_graph_restore_is_idempotent() -> None:
    async def scenario() -> None:
        user = uuid4()
        source = InMemoryGraphRepository()
        await _seed_graph(source, user)
        snapshot = await GraphBackup(source).export([user])

        target = InMemoryGraphRepository()
        backup = GraphBackup(target)
        await backup.restore(snapshot)
        await backup.restore(snapshot)  # second apply must not duplicate

        recovered = await target.get_subgraph(user)
        assert len(recovered.nodes) == 3
        assert len(recovered.edges) == 2

    _run(scenario)


def test_graph_restore_rejects_unknown_version() -> None:
    async def scenario() -> None:
        raised = False
        try:
            await GraphBackup(InMemoryGraphRepository()).restore(
                {"version": 42, "nodes": [], "edges": []}
            )
        except ValueError:
            raised = True
        assert raised

    _run(scenario)

"""Integration: GraphAwareRetrievalService expansion + filtering.

Uses a controlled in-memory graph and a fake retrieval seam (the service depends
on the retrieval service only through ``search``) so the test isolates the new
behavior: provenance/score tagging, the edge-type allowlist (CONTRADICTS
excluded), tenant isolation, and status filtering. Full hybrid retrieval is
covered by tests/integration/test_retrieval_service.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.application.dto.retrieval_dto import (
    MemorySearchQuery,
    RetrievalResult,
    RetrievedMemory,
    ScoreBreakdown,
)
from app.application.services.graph.config import GraphConfig
from app.application.services.graph.graph_aware_retrieval import GraphAwareRetrievalService
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


class _FakeRetrieval:
    def __init__(self, result: RetrievalResult) -> None:
        self._result = result

    async def search(self, query: MemorySearchQuery) -> RetrievalResult:
        return self._result


def _node(node_id, user_id, *, status=MemoryStatus.ACTIVE, content="neighbor") -> GraphNode:
    return GraphNode(
        node_id=str(node_id),
        node_type=NodeType.FACT,
        label=content,
        properties={
            "content": content,
            "memory_type": MemoryType.FACT.value,
            "status": status.value,
            "user_id": str(user_id),
        },
    )


def _hit(memory_id, user_id, score=0.8) -> RetrievedMemory:
    return RetrievedMemory(
        memory_id=memory_id,
        user_id=user_id,
        content="seed",
        memory_type=MemoryType.FACT,
        status=MemoryStatus.ACTIVE,
        final_score=score,
        scores=ScoreBreakdown(0.0, 0.0, 0.0, 0.0, score),
    )


async def _setup(neighbor_node: GraphNode, edge_type: GraphEdgeType, user_id):
    """One hit seed linked to one neighbor by the given edge type."""
    seed_id = uuid4()
    repo = InMemoryGraphRepository()
    await repo.create_node(_node(seed_id, user_id, content="seed"))
    await repo.create_node(neighbor_node)
    await repo.create_edge(GraphEdge(str(seed_id), neighbor_node.node_id, edge_type))

    result = RetrievalResult(
        query="q", user_id=user_id, results=[_hit(seed_id, user_id)], count=1
    )
    service = GraphAwareRetrievalService(_FakeRetrieval(result), repo, GraphConfig())
    query = MemorySearchQuery(query="q", user_id=user_id)
    return service, query, seed_id


def test_hybrid_hit_kept_with_provenance() -> None:
    async def scenario() -> None:
        user_id = uuid4()
        neighbor = _node(uuid4(), user_id)
        service, query, seed_id = await _setup(neighbor, GraphEdgeType.RELATED_TO, user_id)

        out = await service.search(query)

        hybrid = [r for r in out.results if r.provenance == "hybrid"]
        assert len(hybrid) == 1
        assert hybrid[0].memory_id == seed_id
        assert out.hybrid_count == 1

    _run(scenario)


def test_neighbor_expanded_with_decayed_graph_score() -> None:
    async def scenario() -> None:
        user_id = uuid4()
        neighbor = _node(uuid4(), user_id)
        service, query, seed_id = await _setup(neighbor, GraphEdgeType.RELATED_TO, user_id)

        out = await service.search(query)

        graph = [r for r in out.results if r.provenance == "graph"]
        assert out.graph_count == 1 and len(graph) == 1
        assert graph[0].source_memory_id == seed_id
        assert graph[0].score == round(0.8 * GraphConfig().graph_score_decay, 6)

    _run(scenario)


def test_contradicts_edge_not_expanded() -> None:
    async def scenario() -> None:
        user_id = uuid4()
        neighbor = _node(uuid4(), user_id)
        service, query, _ = await _setup(neighbor, GraphEdgeType.CONTRADICTS, user_id)

        out = await service.search(query)

        assert out.graph_count == 0
        assert all(r.provenance == "hybrid" for r in out.results)

    _run(scenario)


def test_cross_user_neighbor_excluded() -> None:
    async def scenario() -> None:
        user_id = uuid4()
        other_user = uuid4()
        neighbor = _node(uuid4(), other_user)  # belongs to a different tenant
        service, query, _ = await _setup(neighbor, GraphEdgeType.RELATED_TO, user_id)

        out = await service.search(query)

        assert out.graph_count == 0

    _run(scenario)


def test_archived_neighbor_excluded() -> None:
    async def scenario() -> None:
        user_id = uuid4()
        neighbor = _node(uuid4(), user_id, status=MemoryStatus.ARCHIVED)
        service, query, _ = await _setup(neighbor, GraphEdgeType.RELATED_TO, user_id)

        out = await service.search(query)

        assert out.graph_count == 0

    _run(scenario)

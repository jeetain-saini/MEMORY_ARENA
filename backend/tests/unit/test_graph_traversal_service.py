"""Unit tests for GraphTraversalService."""

from __future__ import annotations

import asyncio

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.application.services.graph.traversal_service import GraphTraversalService
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository


def _run(coro):
    return asyncio.run(coro)


async def _graph() -> InMemoryGraphRepository:
    repo = InMemoryGraphRepository()
    for n in ("a", "b", "c"):
        await repo.create_node(GraphNode(node_id=n, node_type=NodeType.MEMORY, label=n, properties={}))
    await repo.create_edge(GraphEdge("a", "b", GraphEdgeType.RELATED_TO))
    await repo.create_edge(GraphEdge("b", "c", GraphEdgeType.RELATED_TO))
    return repo


def test_neighbors() -> None:
    async def scenario():
        repo = await _graph()
        service = GraphTraversalService(repo)
        neighbors = await service.neighbors("a")
        assert {n.node_id for n in neighbors} == {"b"}

    _run(scenario())


def test_traverse_depth_two_collects_subgraph() -> None:
    async def scenario():
        repo = await _graph()
        service = GraphTraversalService(repo)
        result = await service.traverse("a", depth=2)
        assert {n.node_id for n in result.nodes} == {"a", "b", "c"}
        assert len(result.edges) == 2
        assert result.depth == 2

    _run(scenario())


def test_traverse_depth_one() -> None:
    async def scenario():
        repo = await _graph()
        service = GraphTraversalService(repo)
        result = await service.traverse("a", depth=1)
        assert {n.node_id for n in result.nodes} == {"a", "b"}

    _run(scenario())


def test_paths() -> None:
    async def scenario():
        repo = await _graph()
        service = GraphTraversalService(repo)
        paths = await service.paths("a", "c", max_depth=4)
        assert paths and paths[0].length == 2

    _run(scenario())


def test_expand() -> None:
    async def scenario():
        repo = await _graph()
        service = GraphTraversalService(repo)
        expanded = await service.expand("a", depth=2)
        assert {n.node_id for n in expanded} == {"b", "c"}

    _run(scenario())

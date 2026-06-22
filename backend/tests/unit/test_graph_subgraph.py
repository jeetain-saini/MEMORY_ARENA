"""Unit tests for GraphRepository.get_subgraph (Stage 16 graph overview)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository

USER = uuid4()
OTHER = uuid4()


def _node(node_id: str, user) -> GraphNode:
    return GraphNode(
        node_id=node_id, node_type=NodeType.FACT, label=node_id,
        properties={"user_id": str(user)},
    )


def test_subgraph_returns_user_nodes_and_edges_among_them() -> None:
    async def scenario() -> None:
        repo = InMemoryGraphRepository()
        await repo.create_node(_node("a", USER))
        await repo.create_node(_node("b", USER))
        await repo.create_node(_node("z", OTHER))  # different tenant
        await repo.create_edge(GraphEdge("a", "b", GraphEdgeType.RELATED_TO))
        await repo.create_edge(GraphEdge("a", "b", GraphEdgeType.CONTRADICTS))
        await repo.create_edge(GraphEdge("a", "b", GraphEdgeType.SUPERSEDES))
        await repo.create_edge(GraphEdge("a", "z", GraphEdgeType.RELATED_TO))  # cross-tenant

        ov = await repo.get_subgraph(USER)
        node_ids = {n.node_id for n in ov.nodes}
        assert node_ids == {"a", "b"}                 # OTHER's node excluded
        types = sorted(e.edge_type.value for e in ov.edges)
        # only edges with both endpoints owned by USER
        assert types == ["contradicts", "related_to", "supersedes"]

    asyncio.run(scenario())


def test_subgraph_empty_for_unknown_user() -> None:
    async def scenario() -> None:
        repo = InMemoryGraphRepository()
        await repo.create_node(_node("a", USER))
        ov = await repo.get_subgraph(uuid4())
        assert ov.nodes == [] and ov.edges == []

    asyncio.run(scenario())

"""Unit tests for graph node/edge counts (Stage 13 graph density)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository

USER_A = uuid4()
USER_B = uuid4()


def _node(node_id: str, user_id) -> GraphNode:
    return GraphNode(
        node_id=node_id,
        node_type=NodeType.MEMORY,
        label=node_id,
        properties={"content": node_id, "user_id": str(user_id)},
    )


def _run(coro):
    return asyncio.run(coro)


def _seed() -> InMemoryGraphRepository:
    repo = InMemoryGraphRepository()
    _run(repo.create_node(_node("a", USER_A)))
    _run(repo.create_node(_node("b", USER_A)))
    _run(repo.create_node(_node("c", USER_B)))
    _run(repo.create_edge(GraphEdge("a", "b", GraphEdgeType.RELATED_TO)))   # both USER_A
    _run(repo.create_edge(GraphEdge("b", "c", GraphEdgeType.RELATED_TO)))   # cross-user
    return repo


def test_count_nodes_global() -> None:
    assert _run(_seed().count_nodes()) == 3


def test_count_nodes_per_user() -> None:
    repo = _seed()
    assert _run(repo.count_nodes(USER_A)) == 2
    assert _run(repo.count_nodes(USER_B)) == 1


def test_count_edges_global() -> None:
    assert _run(_seed().count_edges()) == 2


def test_count_edges_per_user_requires_both_endpoints() -> None:
    repo = _seed()
    # Only the a-b edge has both endpoints owned by USER_A; the cross-user edge
    # is excluded.
    assert _run(repo.count_edges(USER_A)) == 1
    assert _run(repo.count_edges(USER_B)) == 0


def test_counts_on_empty_repo() -> None:
    repo = InMemoryGraphRepository()
    assert _run(repo.count_nodes()) == 0
    assert _run(repo.count_edges()) == 0
    assert _run(repo.count_nodes(USER_A)) == 0

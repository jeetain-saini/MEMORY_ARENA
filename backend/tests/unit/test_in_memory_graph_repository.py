"""Unit tests for InMemoryGraphRepository."""

from __future__ import annotations

import asyncio

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository


def _node(node_id: str, node_type: NodeType = NodeType.MEMORY) -> GraphNode:
    return GraphNode(node_id=node_id, node_type=node_type, label=node_id, properties={"content": node_id})


def _edge(a: str, b: str, t: GraphEdgeType = GraphEdgeType.RELATED_TO) -> GraphEdge:
    return GraphEdge(source_id=a, target_id=b, edge_type=t)


def _run(coro):
    return asyncio.run(coro)


def test_create_and_get_node() -> None:
    repo = InMemoryGraphRepository()
    _run(repo.create_node(_node("a")))
    assert _run(repo.get_node("a")).node_id == "a"
    assert _run(repo.get_node("missing")) is None


def test_update_node() -> None:
    repo = InMemoryGraphRepository()
    _run(repo.create_node(_node("a")))
    _run(repo.update_node(GraphNode(node_id="a", node_type=NodeType.GOAL, label="L", properties={})))
    assert _run(repo.get_node("a")).node_type is NodeType.GOAL


def test_delete_node_removes_incident_edges() -> None:
    repo = InMemoryGraphRepository()
    _run(repo.create_node(_node("a")))
    _run(repo.create_node(_node("b")))
    _run(repo.create_edge(_edge("a", "b")))
    _run(repo.delete_node("a"))
    assert _run(repo.get_node("a")) is None
    assert _run(repo.get_edges("b")) == []


def test_create_and_get_edges() -> None:
    repo = InMemoryGraphRepository()
    for n in ("a", "b"):
        _run(repo.create_node(_node(n)))
    _run(repo.create_edge(_edge("a", "b", GraphEdgeType.SUPPORTS)))
    edges = _run(repo.get_edges("a"))
    assert len(edges) == 1 and edges[0].edge_type is GraphEdgeType.SUPPORTS


def test_delete_edge() -> None:
    repo = InMemoryGraphRepository()
    for n in ("a", "b"):
        _run(repo.create_node(_node(n)))
    _run(repo.create_edge(_edge("a", "b")))
    _run(repo.delete_edge("a", "b", GraphEdgeType.RELATED_TO))
    assert _run(repo.get_edges("a")) == []


def test_find_neighbors_depth_one() -> None:
    repo = InMemoryGraphRepository()
    for n in ("a", "b", "c"):
        _run(repo.create_node(_node(n)))
    _run(repo.create_edge(_edge("a", "b")))
    _run(repo.create_edge(_edge("b", "c")))
    neighbors = _run(repo.find_neighbors("a", depth=1))
    assert {n.node_id for n in neighbors} == {"b"}


def test_find_neighbors_depth_two() -> None:
    repo = InMemoryGraphRepository()
    for n in ("a", "b", "c"):
        _run(repo.create_node(_node(n)))
    _run(repo.create_edge(_edge("a", "b")))
    _run(repo.create_edge(_edge("b", "c")))
    neighbors = _run(repo.find_neighbors("a", depth=2))
    assert {n.node_id for n in neighbors} == {"b", "c"}


def test_find_neighbors_filters_edge_types() -> None:
    repo = InMemoryGraphRepository()
    for n in ("a", "b", "c"):
        _run(repo.create_node(_node(n)))
    _run(repo.create_edge(_edge("a", "b", GraphEdgeType.SUPPORTS)))
    _run(repo.create_edge(_edge("a", "c", GraphEdgeType.RELATED_TO)))
    neighbors = _run(repo.find_neighbors("a", depth=1, edge_types=[GraphEdgeType.SUPPORTS]))
    assert {n.node_id for n in neighbors} == {"b"}


def test_find_paths() -> None:
    repo = InMemoryGraphRepository()
    for n in ("a", "b", "c"):
        _run(repo.create_node(_node(n)))
    _run(repo.create_edge(_edge("a", "b")))
    _run(repo.create_edge(_edge("b", "c")))
    paths = _run(repo.find_paths("a", "c", max_depth=4))
    assert paths
    assert paths[0].length == 2

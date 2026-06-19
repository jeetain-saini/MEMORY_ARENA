"""Unit tests for GraphRelationshipService edge derivation."""

from __future__ import annotations

from app.application.dto.graph_dto import GraphEdgeType, GraphNode, NodeType
from app.application.services.graph.relationship_service import GraphRelationshipService


def _node(node_id: str, content: str, node_type: NodeType) -> GraphNode:
    return GraphNode(node_id=node_id, node_type=node_type, label=content[:20], properties={"content": content})


def test_shared_entities_yield_related_to() -> None:
    a = _node("a", "python and langchain tooling", NodeType.FACT)
    b = _node("b", "langchain agents overview", NodeType.FACT)
    edges = GraphRelationshipService().derive_edges(a, [b])
    assert len(edges) == 1
    assert edges[0].edge_type is GraphEdgeType.RELATED_TO
    assert "langchain" in edges[0].properties["shared_entities"]


def test_goal_project_yields_supports_directed() -> None:
    goal = _node("g", "ship the product", NodeType.GOAL)
    project = _node("p", "product launch project", NodeType.PROJECT)
    [edge] = GraphRelationshipService().derive_edges(goal, [project])
    assert edge.edge_type is GraphEdgeType.SUPPORTS
    assert edge.source_id == "g" and edge.target_id == "p"


def test_skill_project_yields_used_in() -> None:
    skill = _node("s", "python programming skill", NodeType.SKILL)
    project = _node("p", "python backend project", NodeType.PROJECT)
    [edge] = GraphRelationshipService().derive_edges(skill, [project])
    assert edge.edge_type is GraphEdgeType.USED_IN
    assert edge.source_id == "s" and edge.target_id == "p"


def test_rule_applies_in_reverse_orientation() -> None:
    project = _node("p", "python backend project", NodeType.PROJECT)
    skill = _node("s", "python programming skill", NodeType.SKILL)
    [edge] = GraphRelationshipService().derive_edges(project, [skill])
    # Direction must still be skill -> project (USED_IN).
    assert edge.edge_type is GraphEdgeType.USED_IN
    assert edge.source_id == "s" and edge.target_id == "p"


def test_no_shared_entities_no_edges() -> None:
    a = _node("a", "apples and oranges", NodeType.FACT)
    b = _node("b", "quantum mechanics", NodeType.FACT)
    assert GraphRelationshipService().derive_edges(a, [b]) == []

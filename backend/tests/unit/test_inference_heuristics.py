"""Unit tests for deterministic relationship-inference heuristics."""

from __future__ import annotations

from app.application.dto.graph_dto import GraphEdgeType
from app.application.services.maintenance.inference_heuristics import infer_relationship
from app.domain.value_objects.memory_type import MemoryType


def _infer(src, src_t, tgt, tgt_t):
    return infer_relationship(
        source_content=src, source_type=src_t, target_content=tgt, target_type=tgt_t
    )


def test_unrelated_returns_none() -> None:
    assert _infer("python data science", MemoryType.FACT, "cats love fish", MemoryType.FACT) is None


def test_depends_on_by_type_pair() -> None:
    rel = _infer(
        "ship the analytics platform project", MemoryType.PROJECT,
        "analytics platform requires python skill", MemoryType.SKILL,
    )
    assert rel is not None
    assert rel.edge_type is GraphEdgeType.DEPENDS_ON


def test_depends_on_by_marker() -> None:
    rel = _infer(
        "the dashboard requires postgres database", MemoryType.FACT,
        "postgres database is configured", MemoryType.FACT,
    )
    assert rel is not None
    assert rel.edge_type is GraphEdgeType.DEPENDS_ON


def test_derived_from_by_type() -> None:
    rel = _infer(
        "attended the kubernetes workshop yesterday", MemoryType.EXPERIENCE,
        "kubernetes orchestrates containers", MemoryType.FACT,
    )
    assert rel is not None
    assert rel.edge_type is GraphEdgeType.DERIVED_FROM


def test_reinforces_same_type() -> None:
    rel = _infer(
        "user prefers dark mode interfaces", MemoryType.PREFERENCE,
        "user prefers dark mode everywhere", MemoryType.PREFERENCE,
    )
    assert rel is not None
    assert rel.edge_type is GraphEdgeType.REINFORCES


def test_related_to_fallback() -> None:
    rel = _infer(
        "python powers the recommendation engine", MemoryType.FACT,
        "the recommendation engine uses python", MemoryType.PREFERENCE,
    )
    assert rel is not None
    # Different non-matching types, shared entities → RELATED_TO fallback.
    assert rel.edge_type is GraphEdgeType.RELATED_TO


def test_marker_boosts_confidence() -> None:
    rel = _infer(
        "the api requires authentication tokens", MemoryType.FACT,
        "authentication tokens api gateway", MemoryType.FACT,
    )
    assert rel is not None
    assert rel.confidence > 0.0


def test_confidence_in_unit_range() -> None:
    rel = _infer(
        "python python python data", MemoryType.FACT,
        "python python python data", MemoryType.FACT,
    )
    assert rel is not None
    assert 0.0 <= rel.confidence <= 1.0

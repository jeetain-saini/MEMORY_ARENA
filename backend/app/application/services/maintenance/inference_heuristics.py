"""Deterministic, lexical relationship inference (Stage 11 Phase B).

Pure functions — no LLM, no I/O — that decide whether two memories are related,
which edge type fits, and with what confidence. Mirrors the lexical approach
already used by ``GraphRelationshipService``: relatedness is the Jaccard overlap
of significant entities; the edge *type* is chosen from the memory-type pair and
marker words, with a small confidence boost when a marker is present.

Edge types considered: DEPENDS_ON, DERIVED_FROM, REINFORCES, RELATED_TO.
RELATED_TO is the fallback (and is owned by GraphSyncService); the three semantic
types are externally managed and preserved across graph sync.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.graph_dto import GraphEdgeType
from app.application.services.graph.mapping import extract_entities
from app.domain.value_objects.memory_type import MemoryType

# Marker words that signal a specific relationship, independent of memory type.
_DEPENDS_MARKERS = frozenset(
    {"requires", "require", "needs", "need", "depends", "dependency", "prerequisite", "blocked"}
)
_DERIVED_MARKERS = frozenset(
    {"based", "derived", "from", "after", "learned", "because", "result", "following"}
)
_REINFORCES_MARKERS = frozenset(
    {"again", "confirms", "confirm", "still", "reaffirm", "reinforces", "consistently", "also"}
)

_MARKER_BOOST = 0.15


@dataclass(frozen=True)
class InferredRelationship:
    edge_type: GraphEdgeType
    confidence: float


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in text.split()}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _classify_type(
    source_type: MemoryType,
    target_content: str,
    source_content: str,
    target_type: MemoryType,
) -> tuple[GraphEdgeType, bool]:
    """Return (edge_type, marker_present)."""
    words = _tokens(source_content) | _tokens(target_content)

    # DEPENDS_ON: a goal/project that requires a skill/fact, or a dependency marker.
    type_depends = source_type in (MemoryType.GOAL, MemoryType.PROJECT) and target_type in (
        MemoryType.SKILL,
        MemoryType.FACT,
    )
    if words & _DEPENDS_MARKERS or type_depends:
        return GraphEdgeType.DEPENDS_ON, bool(words & _DEPENDS_MARKERS)

    # DERIVED_FROM: an experience derived from a fact/project, or a derivation marker.
    type_derived = source_type is MemoryType.EXPERIENCE and target_type in (
        MemoryType.FACT,
        MemoryType.PROJECT,
    )
    if words & _DERIVED_MARKERS or type_derived:
        return GraphEdgeType.DERIVED_FROM, bool(words & _DERIVED_MARKERS)

    # REINFORCES: same-type memories restating/confirming each other.
    if source_type is target_type or (words & _REINFORCES_MARKERS):
        return GraphEdgeType.REINFORCES, bool(words & _REINFORCES_MARKERS)

    return GraphEdgeType.RELATED_TO, False


def infer_relationship(
    *,
    source_content: str,
    source_type: MemoryType,
    target_content: str,
    target_type: MemoryType,
    min_entity_length: int = 3,
) -> InferredRelationship | None:
    """Infer the relationship between two memories, or ``None`` if unrelated."""
    source_entities = extract_entities(source_content, min_length=min_entity_length)
    target_entities = extract_entities(target_content, min_length=min_entity_length)
    base = _jaccard(source_entities, target_entities)
    if base <= 0.0:
        return None

    edge_type, marker = _classify_type(source_type, target_content, source_content, target_type)
    confidence = min(1.0, round(base + (_MARKER_BOOST if marker else 0.0), 4))
    return InferredRelationship(edge_type=edge_type, confidence=confidence)

"""Configuration for the knowledge-graph layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.application.dto.graph_dto import GraphEdgeType, NodeType

# Directed type-pair rules: (from_type, to_type) -> edge_type.
# When two related memories match a pair (in either orientation), the derived
# edge uses this type and points from `from_type` to `to_type`.
DEFAULT_TYPE_PAIR_RULES: list[tuple[NodeType, NodeType, GraphEdgeType]] = [
    (NodeType.GOAL, NodeType.PROJECT, GraphEdgeType.SUPPORTS),
    (NodeType.SKILL, NodeType.PROJECT, GraphEdgeType.USED_IN),
    (NodeType.SKILL, NodeType.GOAL, GraphEdgeType.SUPPORTS),
]


# Edge types eligible for graph-aware retrieval expansion. CONTRADICTS is
# deliberately excluded: surfacing a contradicting memory as supporting context
# would undermine Stage 8 conflict detection.
DEFAULT_EXPANSION_EDGE_TYPES: tuple[GraphEdgeType, ...] = (
    GraphEdgeType.RELATED_TO,
    GraphEdgeType.SUPPORTS,
    GraphEdgeType.USED_IN,
    GraphEdgeType.DEPENDS_ON,
    GraphEdgeType.DERIVED_FROM,
    GraphEdgeType.REINFORCES,
)


# Edge types written by other services (consolidation, relationship inference)
# rather than derived by GraphSyncService. Sync must NOT delete these during its
# re-derivation, or it would destroy externally-managed relationships. RELATED_TO
# / SUPPORTS / USED_IN are intentionally absent: sync owns and re-derives them.
DEFAULT_EXTERNALLY_MANAGED_EDGE_TYPES: frozenset[GraphEdgeType] = frozenset(
    {
        GraphEdgeType.CONTRADICTS,   # consolidation (Stage 10 P2)
        GraphEdgeType.SUPERSEDES,    # contradiction resolution (Stage 16)
        GraphEdgeType.DEPENDS_ON,    # relationship inference (Stage 11 P B)
        GraphEdgeType.DERIVED_FROM,  # relationship inference
        GraphEdgeType.REINFORCES,    # relationship inference
    }
)


@dataclass(frozen=True)
class GraphConfig:
    # Relationship derivation
    min_shared_entities: int = 1
    min_entity_length: int = 3
    type_pair_rules: list[tuple[NodeType, NodeType, GraphEdgeType]] = field(
        default_factory=lambda: list(DEFAULT_TYPE_PAIR_RULES)
    )
    # Sync: cap the candidate set compared for edge derivation per write, so a
    # single memory write stays O(K) instead of O(N) in a user's memory count.
    max_sync_candidates: int = 50
    # Traversal / expansion
    expansion_depth: int = 1
    max_neighbors: int = 25
    graph_score_decay: float = 0.5
    max_paths: int = 10
    expansion_edge_types: tuple[GraphEdgeType, ...] = DEFAULT_EXPANSION_EDGE_TYPES
    externally_managed_edge_types: frozenset[GraphEdgeType] = (
        DEFAULT_EXTERNALLY_MANAGED_EDGE_TYPES
    )

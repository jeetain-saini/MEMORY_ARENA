"""GraphRelationshipService — derive edges between memory nodes.

Two memories are related when they share significant entities (keywords). The
edge *type* is chosen by configurable type-pair rules:

    Python  / LangChain   (shared entities)   -> RELATED_TO   (default)
    Goal    / Project                          -> SUPPORTS
    Skill   / Project                          -> USED_IN

No LLM — entities are extracted lexically. Rules are directed and applied in
either orientation.
"""

from __future__ import annotations

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode
from app.application.services.graph.config import GraphConfig
from app.application.services.graph.mapping import extract_entities


class GraphRelationshipService:
    def __init__(self, config: GraphConfig | None = None) -> None:
        self._config = config or GraphConfig()

    def derive_edges(self, source: GraphNode, candidates: list[GraphNode]) -> list[GraphEdge]:
        source_entities = self._entities(source)
        if not source_entities:
            return []

        edges: list[GraphEdge] = []
        for candidate in candidates:
            if candidate.node_id == source.node_id:
                continue
            shared = source_entities & self._entities(candidate)
            if len(shared) < self._config.min_shared_entities:
                continue

            edge_type, src, tgt = self._resolve(source, candidate)
            union = source_entities | self._entities(candidate)
            weight = round(len(shared) / len(union), 4) if union else 0.0
            edges.append(
                GraphEdge(
                    source_id=src.node_id,
                    target_id=tgt.node_id,
                    edge_type=edge_type,
                    weight=weight,
                    properties={"shared_entities": sorted(shared)},
                )
            )
        return edges

    def _entities(self, node: GraphNode) -> set[str]:
        return extract_entities(
            str(node.properties.get("content", "")), min_length=self._config.min_entity_length
        )

    def _resolve(
        self, source: GraphNode, candidate: GraphNode
    ) -> tuple[GraphEdgeType, GraphNode, GraphNode]:
        for from_type, to_type, edge_type in self._config.type_pair_rules:
            if source.node_type == from_type and candidate.node_type == to_type:
                return edge_type, source, candidate
            if source.node_type == to_type and candidate.node_type == from_type:
                return edge_type, candidate, source
        return GraphEdgeType.RELATED_TO, source, candidate

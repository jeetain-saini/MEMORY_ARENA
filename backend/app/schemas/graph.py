"""Pydantic schemas for the knowledge-graph API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.dto.graph_dto import (
    GraphAwareResult,
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphTraversalResult,
    NodeType,
)
from app.application.dto.retrieval_dto import MemorySearchQuery, RetrievalFilters
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.schemas.retrieval import RetrievalFiltersSchema


# --- requests --------------------------------------------------------------
class GraphSearchRequestSchema(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    user_id: UUID
    top_k: int = Field(default=10, ge=1, le=200)
    expand_depth: int = Field(default=1, ge=1, le=4)
    filters: RetrievalFiltersSchema | None = None

    def to_query(self) -> MemorySearchQuery:
        filters = self.filters.to_dto() if self.filters else RetrievalFilters()
        return MemorySearchQuery(
            query=self.query, user_id=self.user_id, filters=filters, top_k=self.top_k
        )


class GraphTraverseRequestSchema(BaseModel):
    node_id: str
    depth: int = Field(default=1, ge=1, le=5)


# --- responses -------------------------------------------------------------
class GraphNodeSchema(BaseModel):
    node_id: str
    node_type: NodeType
    label: str
    properties: dict[str, Any]

    @classmethod
    def from_dto(cls, node: GraphNode) -> "GraphNodeSchema":
        return cls(
            node_id=node.node_id, node_type=node.node_type,
            label=node.label, properties=node.properties,
        )


class GraphEdgeSchema(BaseModel):
    source_id: str
    target_id: str
    edge_type: GraphEdgeType
    weight: float
    properties: dict[str, Any]

    @classmethod
    def from_dto(cls, edge: GraphEdge) -> "GraphEdgeSchema":
        return cls(
            source_id=edge.source_id, target_id=edge.target_id,
            edge_type=edge.edge_type, weight=edge.weight, properties=edge.properties,
        )


class GraphTraversalResultSchema(BaseModel):
    root_id: str
    depth: int
    nodes: list[GraphNodeSchema]
    edges: list[GraphEdgeSchema]

    @classmethod
    def from_dto(cls, dto: GraphTraversalResult) -> "GraphTraversalResultSchema":
        return cls(
            root_id=dto.root_id, depth=dto.depth,
            nodes=[GraphNodeSchema.from_dto(n) for n in dto.nodes],
            edges=[GraphEdgeSchema.from_dto(e) for e in dto.edges],
        )


class ExpandedMemorySchema(BaseModel):
    memory_id: UUID
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    score: float
    provenance: str
    source_memory_id: UUID | None = None


class GraphAwareResultSchema(BaseModel):
    query: str
    user_id: UUID
    hybrid_count: int
    graph_count: int
    results: list[ExpandedMemorySchema]

    @classmethod
    def from_dto(cls, dto: GraphAwareResult) -> "GraphAwareResultSchema":
        return cls(
            query=dto.query, user_id=dto.user_id,
            hybrid_count=dto.hybrid_count, graph_count=dto.graph_count,
            results=[
                ExpandedMemorySchema(
                    memory_id=r.memory_id, content=r.content, memory_type=r.memory_type,
                    status=r.status, score=r.score, provenance=r.provenance,
                    source_memory_id=r.source_memory_id,
                )
                for r in dto.results
            ],
        )


class GraphMemoryViewSchema(BaseModel):
    node: GraphNodeSchema | None
    neighbors: list[GraphNodeSchema]
    edges: list[GraphEdgeSchema]

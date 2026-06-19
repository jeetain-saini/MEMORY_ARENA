"""Knowledge-graph DTOs.

Plain dataclasses describing graph memory: nodes (one per memory), typed edges
between them, paths, traversal results, and the provenance-tagged result of
graph-aware retrieval. No Neo4j or pydantic here — those live at the edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


class NodeType(str, Enum):
    MEMORY = "memory"
    GOAL = "goal"
    SKILL = "skill"
    PROJECT = "project"
    PREFERENCE = "preference"
    FACT = "fact"


class GraphEdgeType(str, Enum):
    RELATED_TO = "related_to"
    SUPPORTS = "supports"
    USED_IN = "used_in"
    DEPENDS_ON = "depends_on"
    DERIVED_FROM = "derived_from"
    REINFORCES = "reinforces"
    CONTRADICTS = "contradicts"


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: NodeType
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: GraphEdgeType
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphPath:
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @property
    def length(self) -> int:
        return len(self.edges)


@dataclass(frozen=True)
class GraphTraversalResult:
    root_id: str
    depth: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@dataclass(frozen=True)
class ExpandedMemory:
    memory_id: UUID
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    score: float
    provenance: str            # "hybrid" | "graph"
    source_memory_id: UUID | None = None  # the seed a graph memory expanded from


@dataclass(frozen=True)
class GraphAwareResult:
    query: str
    user_id: UUID
    results: list[ExpandedMemory]
    hybrid_count: int
    graph_count: int

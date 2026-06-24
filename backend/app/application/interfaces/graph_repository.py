"""GraphRepository port — persistence & traversal for the knowledge graph.

The application depends on this abstraction; a real ``Neo4jGraphRepository`` and
an offline ``InMemoryGraphRepository`` implement it, selected by configuration.
All methods are async (real backends do I/O).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.graph_dto import (
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphOverview,
    GraphPath,
)


class GraphRepository(ABC):
    # --- nodes ------------------------------------------------------------
    @abstractmethod
    async def create_node(self, node: GraphNode) -> GraphNode: ...

    @abstractmethod
    async def update_node(self, node: GraphNode) -> GraphNode: ...

    @abstractmethod
    async def upsert_node(self, node: GraphNode) -> GraphNode: ...

    @abstractmethod
    async def delete_node(self, node_id: str) -> None: ...

    @abstractmethod
    async def get_node(self, node_id: str) -> GraphNode | None: ...

    # --- edges ------------------------------------------------------------
    @abstractmethod
    async def create_edge(self, edge: GraphEdge) -> GraphEdge: ...

    @abstractmethod
    async def delete_edge(
        self, source_id: str, target_id: str, edge_type: GraphEdgeType
    ) -> None: ...

    @abstractmethod
    async def get_edges(
        self,
        node_id: str,
        exclude_types: frozenset[GraphEdgeType] | None = None,
    ) -> list[GraphEdge]: ...

    # --- traversal --------------------------------------------------------
    @abstractmethod
    async def find_neighbors(
        self, node_id: str, *, depth: int = 1, edge_types: list[GraphEdgeType] | None = None
    ) -> list[GraphNode]: ...

    @abstractmethod
    async def find_paths(
        self, source_id: str, target_id: str, *, max_depth: int = 4
    ) -> list[GraphPath]: ...

    # --- overview (Stage 16 graph explorer) -------------------------------
    @abstractmethod
    async def get_subgraph(self, user_id: UUID, *, limit: int | None = None) -> GraphOverview:
        """A tenant's nodes plus the edges among them (one payload).

        ``limit`` caps the number of nodes returned (and the edges to those among
        the inflated set) — large-graph protection for the overview API. ``None``
        (default) returns the full subgraph, which the maintenance snapshot needs.
        """

    # --- counts (Stage 13 observability: graph density) -------------------
    @abstractmethod
    async def count_nodes(self, user_id: UUID | None = None) -> int:
        """Count nodes, optionally scoped to one tenant's ``user_id`` property."""

    @abstractmethod
    async def count_edges(self, user_id: UUID | None = None) -> int:
        """Count edges whose endpoints belong to ``user_id`` (or all if None)."""

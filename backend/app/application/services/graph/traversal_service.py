"""GraphTraversalService — depth-limited traversal over the knowledge graph.

Thin orchestration over the GraphRepository: neighbor search, depth-limited
subgraph traversal, path search, and related-memory expansion. The heavy lifting
(BFS / Cypher) lives in the repository implementations.
"""

from __future__ import annotations

from app.application.dto.auth_dto import AuthPrincipal
from app.application.dto.graph_dto import (
    GraphEdgeType,
    GraphNode,
    GraphPath,
    GraphTraversalResult,
)
from app.application.exceptions import ResourceNotFoundForCaller
from app.application.interfaces.graph_repository import GraphRepository
from app.application.services.authorization import authorize_owner
from app.application.services.graph.config import GraphConfig


class GraphTraversalService:
    def __init__(
        self,
        repository: GraphRepository,
        config: GraphConfig | None = None,
        principal: AuthPrincipal | None = None,
    ) -> None:
        self._repo = repository
        self._config = config or GraphConfig()
        self._principal = principal

    def _authorize_node(self, node: GraphNode | None) -> None:
        """Ownership guard for a graph node (no-op when auth is disabled)."""
        if self._principal is None:
            return
        if node is None:
            raise ResourceNotFoundForCaller()
        owner = node.properties.get("user_id")
        if str(owner) != str(self._principal.user_id):
            raise ResourceNotFoundForCaller()

    async def neighbors(
        self, node_id: str, *, edge_types: list[GraphEdgeType] | None = None
    ) -> list[GraphNode]:
        return await self._repo.find_neighbors(node_id, depth=1, edge_types=edge_types)

    async def traverse(self, node_id: str, *, depth: int = 1) -> GraphTraversalResult:
        root = await self._repo.get_node(node_id)
        self._authorize_node(root)
        neighbor_nodes = await self._repo.find_neighbors(node_id, depth=depth)

        nodes: dict[str, GraphNode] = {}
        if root is not None:
            nodes[root.node_id] = root
        for node in neighbor_nodes:
            nodes[node.node_id] = node

        # Collect edges whose endpoints are both within the traversed set.
        edges: dict[tuple[str, str, str], object] = {}
        for nid in list(nodes):
            for edge in await self._repo.get_edges(nid):
                if edge.source_id in nodes and edge.target_id in nodes:
                    edges[(edge.source_id, edge.target_id, edge.edge_type.value)] = edge

        return GraphTraversalResult(
            root_id=node_id, depth=depth, nodes=list(nodes.values()), edges=list(edges.values())  # type: ignore[arg-type]
        )

    async def paths(
        self, source_id: str, target_id: str, *, max_depth: int = 4
    ) -> list[GraphPath]:
        return await self._repo.find_paths(source_id, target_id, max_depth=max_depth)

    async def expand(self, node_id: str, *, depth: int | None = None) -> list[GraphNode]:
        return await self._repo.find_neighbors(
            node_id, depth=depth or self._config.expansion_depth
        )

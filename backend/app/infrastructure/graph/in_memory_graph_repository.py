"""InMemoryGraphRepository — dependency-free graph backend.

An adjacency-based implementation used as the offline/dev default and in tests.
Edges are treated as undirected for neighbor/path traversal (direction is still
recorded on the edge). Mirrors the semantics of the Neo4j backend so services
behave identically regardless of which is wired in.
"""

from __future__ import annotations

from collections import deque
from uuid import UUID

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, GraphPath
from app.application.interfaces.graph_repository import GraphRepository


class InMemoryGraphRepository(GraphRepository):
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[tuple[str, str, str], GraphEdge] = {}

    # --- nodes ------------------------------------------------------------
    async def create_node(self, node: GraphNode) -> GraphNode:
        self._nodes[node.node_id] = node
        return node

    async def update_node(self, node: GraphNode) -> GraphNode:
        self._nodes[node.node_id] = node
        return node

    async def upsert_node(self, node: GraphNode) -> GraphNode:
        self._nodes[node.node_id] = node
        return node

    async def delete_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        self._edges = {
            key: edge
            for key, edge in self._edges.items()
            if edge.source_id != node_id and edge.target_id != node_id
        }

    async def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    # --- edges ------------------------------------------------------------
    async def create_edge(self, edge: GraphEdge) -> GraphEdge:
        self._edges[(edge.source_id, edge.target_id, edge.edge_type.value)] = edge
        return edge

    async def delete_edge(
        self, source_id: str, target_id: str, edge_type: GraphEdgeType
    ) -> None:
        self._edges.pop((source_id, target_id, edge_type.value), None)

    async def get_edges(
        self,
        node_id: str,
        exclude_types: frozenset[GraphEdgeType] | None = None,
    ) -> list[GraphEdge]:
        return [
            edge
            for edge in self._edges.values()
            if (edge.source_id == node_id or edge.target_id == node_id)
            and (exclude_types is None or edge.edge_type not in exclude_types)
        ]

    # --- traversal --------------------------------------------------------
    async def find_neighbors(
        self, node_id: str, *, depth: int = 1, edge_types: list[GraphEdgeType] | None = None
    ) -> list[GraphNode]:
        allowed = {t.value for t in edge_types} if edge_types else None
        visited: set[str] = {node_id}
        frontier: deque[tuple[str, int]] = deque([(node_id, 0)])
        found: list[GraphNode] = []

        while frontier:
            current, dist = frontier.popleft()
            if dist >= depth:
                continue
            for edge in self._adjacent(current, allowed):
                other = edge.target_id if edge.source_id == current else edge.source_id
                if other in visited:
                    continue
                visited.add(other)
                node = self._nodes.get(other)
                if node is not None:
                    found.append(node)
                frontier.append((other, dist + 1))
        return found

    async def find_paths(
        self, source_id: str, target_id: str, *, max_depth: int = 4
    ) -> list[GraphPath]:
        paths: list[GraphPath] = []

        def dfs(current: str, visited: list[str], edges: list[GraphEdge]) -> None:
            if len(edges) > max_depth:
                return
            if current == target_id and edges:
                nodes = [self._nodes[n] for n in visited if n in self._nodes]
                paths.append(GraphPath(nodes=nodes, edges=list(edges)))
                return
            for edge in self._adjacent(current, None):
                other = edge.target_id if edge.source_id == current else edge.source_id
                if other in visited:
                    continue
                dfs(other, visited + [other], edges + [edge])

        if source_id in self._nodes:
            dfs(source_id, [source_id], [])
        return paths

    # --- counts -----------------------------------------------------------
    async def count_nodes(self, user_id: UUID | None = None) -> int:
        return len(self._user_node_ids(user_id))

    async def count_edges(self, user_id: UUID | None = None) -> int:
        if user_id is None:
            return len(self._edges)
        ids = self._user_node_ids(user_id)
        return sum(
            1 for e in self._edges.values() if e.source_id in ids and e.target_id in ids
        )

    def _user_node_ids(self, user_id: UUID | None) -> set[str]:
        if user_id is None:
            return set(self._nodes)
        target = str(user_id)
        return {
            nid
            for nid, node in self._nodes.items()
            if str(node.properties.get("user_id", "")) == target
        }

    # --- helpers ----------------------------------------------------------
    def _adjacent(self, node_id: str, allowed: set[str] | None) -> list[GraphEdge]:
        result = []
        for edge in self._edges.values():
            if edge.source_id != node_id and edge.target_id != node_id:
                continue
            if allowed is not None and edge.edge_type.value not in allowed:
                continue
            result.append(edge)
        return result

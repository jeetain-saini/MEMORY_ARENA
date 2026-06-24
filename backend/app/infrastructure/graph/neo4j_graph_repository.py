"""Neo4jGraphRepository — Cypher-backed knowledge graph.

Implements the GraphRepository port against Neo4j using the async driver owned
by ``Neo4jManager`` (Stage 1). Memory nodes are stored with a common
``:MemoryNode`` label keyed by ``id``; the semantic node type is a property.
Edge types come from the ``GraphEdgeType`` enum, so it is safe to interpolate
their (validated) values into the relationship type of the Cypher statement.

(Exercised against a live Neo4j; unit tests cover the in-memory backend.)
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.graph_dto import (
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphOverview,
    GraphPath,
    NodeType,
)
from app.application.interfaces.graph_repository import GraphRepository
from app.infrastructure.graph.neo4j import Neo4jManager


class Neo4jGraphRepository(GraphRepository):
    def __init__(self, manager: Neo4jManager) -> None:
        self._manager = manager

    @property
    def _driver(self):  # type: ignore[no-untyped-def]
        return self._manager.driver

    async def _run(self, cypher: str, **params):  # type: ignore[no-untyped-def]
        records, _, _ = await self._driver.execute_query(
            cypher, database_=self._manager.database, **params
        )
        return records

    # --- nodes ------------------------------------------------------------
    async def create_node(self, node: GraphNode) -> GraphNode:
        return await self.upsert_node(node)

    async def update_node(self, node: GraphNode) -> GraphNode:
        return await self.upsert_node(node)

    async def upsert_node(self, node: GraphNode) -> GraphNode:
        await self._run(
            "MERGE (n:MemoryNode {id: $id}) "
            "SET n.node_type = $node_type, n.label = $label, n += $properties",
            id=node.node_id,
            node_type=node.node_type.value,
            label=node.label,
            properties=node.properties,
        )
        return node

    async def delete_node(self, node_id: str) -> None:
        await self._run("MATCH (n:MemoryNode {id: $id}) DETACH DELETE n", id=node_id)

    async def get_node(self, node_id: str) -> GraphNode | None:
        records = await self._run("MATCH (n:MemoryNode {id: $id}) RETURN n", id=node_id)
        if not records:
            return None
        return self._to_node(records[0]["n"])

    # --- edges ------------------------------------------------------------
    async def create_edge(self, edge: GraphEdge) -> GraphEdge:
        rel_type = edge.edge_type.value.upper()  # enum value -> safe literal
        await self._run(
            "MATCH (a:MemoryNode {id: $source}), (b:MemoryNode {id: $target}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            "SET r.weight = $weight, r += $properties",
            source=edge.source_id,
            target=edge.target_id,
            weight=edge.weight,
            properties=edge.properties,
        )
        return edge

    async def delete_edge(
        self, source_id: str, target_id: str, edge_type: GraphEdgeType
    ) -> None:
        rel_type = edge_type.value.upper()
        await self._run(
            "MATCH (a:MemoryNode {id: $source})-"
            f"[r:{rel_type}]->(b:MemoryNode {{id: $target}}) DELETE r",
            source=source_id,
            target=target_id,
        )

    async def get_edges(
        self,
        node_id: str,
        exclude_types: frozenset[GraphEdgeType] | None = None,
    ) -> list[GraphEdge]:
        # Return the *true* stored direction (startNode/endNode), so callers can
        # delete an edge by its (source, target, type) key regardless of which
        # endpoint was queried.
        if exclude_types:
            excluded = [t.value.upper() for t in exclude_types]
            records = await self._run(
                "MATCH (a:MemoryNode {id: $id})-[r]-(:MemoryNode) "
                "WHERE NOT type(r) IN $excluded "
                "RETURN startNode(r).id AS src, endNode(r).id AS dst, "
                "type(r) AS t, r.weight AS w, properties(r) AS p",
                id=node_id,
                excluded=excluded,
            )
        else:
            records = await self._run(
                "MATCH (a:MemoryNode {id: $id})-[r]-(:MemoryNode) "
                "RETURN startNode(r).id AS src, endNode(r).id AS dst, "
                "type(r) AS t, r.weight AS w, properties(r) AS p",
                id=node_id,
            )
        return [self._to_edge(rec) for rec in records]

    # --- traversal --------------------------------------------------------
    async def find_neighbors(
        self, node_id: str, *, depth: int = 1, edge_types: list[GraphEdgeType] | None = None
    ) -> list[GraphNode]:
        depth = max(1, int(depth))
        rel_filter = ""
        if edge_types:
            rel_filter = ":" + "|".join(t.value.upper() for t in edge_types)
        records = await self._run(
            f"MATCH (n:MemoryNode {{id: $id}})-[{rel_filter}*1..{depth}]-(m:MemoryNode) "
            "RETURN DISTINCT m",
            id=node_id,
        )
        return [self._to_node(rec["m"]) for rec in records]

    async def find_paths(
        self, source_id: str, target_id: str, *, max_depth: int = 4
    ) -> list[GraphPath]:
        max_depth = max(1, int(max_depth))
        records = await self._run(
            f"MATCH p = (a:MemoryNode {{id: $source}})-[*1..{max_depth}]-(b:MemoryNode {{id: $target}}) "
            "RETURN p LIMIT 25",
            source=source_id,
            target=target_id,
        )
        paths: list[GraphPath] = []
        for rec in records:
            path = rec["p"]
            nodes = [self._to_node(n) for n in path.nodes]
            edges = [
                GraphEdge(
                    source_id=rel.start_node["id"],
                    target_id=rel.end_node["id"],
                    edge_type=self._edge_type(rel.type),
                    weight=rel.get("weight", 1.0),
                    properties=dict(rel),
                )
                for rel in path.relationships
            ]
            paths.append(GraphPath(nodes=nodes, edges=edges))
        return paths

    # --- overview (Stage 16 graph explorer) -------------------------------
    async def get_subgraph(self, user_id: UUID, *, limit: int | None = None) -> GraphOverview:
        uid = str(user_id)
        if limit is None:
            node_records = await self._run(
                "MATCH (n:MemoryNode {user_id: $uid}) RETURN n", uid=uid
            )
            edge_records = await self._run(
                "MATCH (a:MemoryNode {user_id: $uid})-[r]->(b:MemoryNode {user_id: $uid}) "
                "RETURN startNode(r).id AS src, endNode(r).id AS dst, "
                "type(r) AS t, r.weight AS w, properties(r) AS p",
                uid=uid,
            )
        else:
            # Large-graph protection: cap nodes at the DB (deterministic ORDER BY)
            # and only return edges among the capped node set.
            node_records = await self._run(
                "MATCH (n:MemoryNode {user_id: $uid}) RETURN n ORDER BY n.id LIMIT $lim",
                uid=uid, lim=limit,
            )
            ids = [rec["n"]["id"] for rec in node_records]
            edge_records = await self._run(
                "MATCH (a:MemoryNode)-[r]->(b:MemoryNode) "
                "WHERE a.id IN $ids AND b.id IN $ids "
                "RETURN startNode(r).id AS src, endNode(r).id AS dst, "
                "type(r) AS t, r.weight AS w, properties(r) AS p",
                ids=ids,
            )
        return GraphOverview(
            nodes=[self._to_node(rec["n"]) for rec in node_records],
            edges=[self._to_edge(rec) for rec in edge_records],
        )

    # --- counts (Stage 13 observability: graph density) -------------------
    async def count_nodes(self, user_id: UUID | None = None) -> int:
        uid = str(user_id) if user_id is not None else None
        records = await self._run(
            "MATCH (n:MemoryNode) WHERE $uid IS NULL OR n.user_id = $uid "
            "RETURN count(n) AS c",
            uid=uid,
        )
        return int(records[0]["c"]) if records else 0

    async def count_edges(self, user_id: UUID | None = None) -> int:
        uid = str(user_id) if user_id is not None else None
        records = await self._run(
            "MATCH (a:MemoryNode)-[r]->(b:MemoryNode) "
            "WHERE $uid IS NULL OR (a.user_id = $uid AND b.user_id = $uid) "
            "RETURN count(r) AS c",
            uid=uid,
        )
        return int(records[0]["c"]) if records else 0

    # --- mapping helpers --------------------------------------------------
    @staticmethod
    def _to_node(record) -> GraphNode:  # type: ignore[no-untyped-def]
        data = dict(record)
        node_type = data.pop("node_type", NodeType.MEMORY.value)
        label = data.pop("label", "")
        node_id = data.pop("id")
        return GraphNode(
            node_id=node_id,
            node_type=NodeType(node_type),
            label=label,
            properties=data,
        )

    def _to_edge(self, rec) -> GraphEdge:  # type: ignore[no-untyped-def]
        return GraphEdge(
            source_id=rec["src"],
            target_id=rec["dst"],
            edge_type=self._edge_type(rec["t"]),
            weight=rec.get("w") or 1.0,
            properties=dict(rec.get("p") or {}),
        )

    @staticmethod
    def _edge_type(raw: str) -> GraphEdgeType:
        try:
            return GraphEdgeType(raw.lower())
        except ValueError:
            return GraphEdgeType.RELATED_TO

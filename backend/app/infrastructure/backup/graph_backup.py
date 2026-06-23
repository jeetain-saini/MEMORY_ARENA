"""GraphBackup — portable logical backup & restore for the knowledge graph.

Exports a tenant's (or several tenants') subgraph — every node and the edges
among them — into a JSON-serializable snapshot, and restores it by re-creating
those nodes and edges through the :class:`GraphRepository` port. Backend-agnostic
(same code for Neo4j in production and the in-memory graph in tests), so the
round-trip is verifiable offline.

This is the logical tier of graph DR; the physical tier (``neo4j-admin database
dump``) lives in ``scripts/backup_neo4j.sh`` for byte-exact production backups.
Restore is upsert-based (``upsert_node`` + ``create_edge``), so re-applying a
snapshot is idempotent.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType
from app.application.interfaces.graph_repository import GraphRepository

SNAPSHOT_VERSION = 1


class GraphBackup:
    def __init__(self, graph_repo: GraphRepository) -> None:
        self._graph = graph_repo

    async def export(self, user_ids: list[UUID]) -> dict[str, Any]:
        """Export the union of the given tenants' subgraphs to a snapshot."""
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        for user_id in user_ids:
            overview = await self._graph.get_subgraph(user_id)
            for node in overview.nodes:
                nodes[node.node_id] = {
                    "node_id": node.node_id,
                    "node_type": node.node_type.value,
                    "label": node.label,
                    "properties": node.properties,
                }
            for edge in overview.edges:
                key = (edge.source_id, edge.target_id, edge.edge_type.value)
                edges[key] = {
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "edge_type": edge.edge_type.value,
                    "weight": edge.weight,
                    "properties": edge.properties,
                }
        return {
            "version": SNAPSHOT_VERSION,
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
            "counts": {"nodes": len(nodes), "edges": len(edges)},
        }

    async def restore(self, snapshot: dict[str, Any]) -> dict[str, int]:
        """Re-create nodes and edges from ``snapshot`` (idempotent upsert)."""
        if snapshot.get("version") != SNAPSHOT_VERSION:
            raise ValueError(f"unsupported snapshot version: {snapshot.get('version')!r}")
        for raw in snapshot["nodes"]:
            await self._graph.upsert_node(
                GraphNode(
                    node_id=raw["node_id"],
                    node_type=NodeType(raw["node_type"]),
                    label=raw["label"],
                    properties=dict(raw.get("properties") or {}),
                )
            )
        for raw in snapshot["edges"]:
            await self._graph.create_edge(
                GraphEdge(
                    source_id=raw["source_id"],
                    target_id=raw["target_id"],
                    edge_type=GraphEdgeType(raw["edge_type"]),
                    weight=raw.get("weight", 1.0),
                    properties=dict(raw.get("properties") or {}),
                )
            )
        return {"nodes": len(snapshot["nodes"]), "edges": len(snapshot["edges"])}

"""GraphSnapshot — one batched subgraph read per tenant (Stage 18.1).

The Stage 17 intelligence engines read graph edges *per memory*: both
``evolve_importance_for_user`` and the :class:`ForgettingEngine` issued one
``get_edges`` call for every active memory, so a tenant with ``N`` memories cost
``N`` graph round-trips on every maintenance pass — O(N) I/O that dominated
large-tenant cycles. :class:`GraphSnapshotProvider` fetches the tenant's entire
subgraph in a single ``get_subgraph`` call and serves degree / isolation / edge
lookups from an in-memory adjacency index, collapsing those ``N`` round-trips to
one.

The engines accept an optional :class:`GraphSnapshot`; when none is supplied they
fall back to live per-memory reads, so every existing call site keeps working
unchanged. The snapshot is read-only — engines that *mutate* the graph (promotion,
clustering) still write through the repository, and a fresh snapshot is taken
after those mutations when a later step needs the updated topology.

Equivalence note: ``get_subgraph(user_id)`` returns the edges whose endpoints are
both the tenant's nodes. Every intelligence edge (CLUSTER_MEMBER, PROMOTED_FROM,
CONTRADICTS, SUPERSEDES) is intra-tenant, so for the per-tenant maintenance cycle
the snapshot's adjacency is identical to summing per-memory ``get_edges`` — only
the I/O shape changes, not the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.dto.graph_dto import GraphEdge, GraphOverview
from app.application.interfaces.graph_repository import GraphRepository


@dataclass(frozen=True)
class GraphSnapshot:
    """An immutable, indexed view of one tenant's subgraph.

    Built once per maintenance pass from a single ``get_subgraph`` payload. All
    lookups are O(1)/O(degree) against the in-memory adjacency map — no I/O.
    """

    _adjacency: dict[str, tuple[GraphEdge, ...]]
    _max_degree: int

    @classmethod
    def from_overview(cls, overview: GraphOverview) -> "GraphSnapshot":
        adjacency: dict[str, list[GraphEdge]] = {
            node.node_id: [] for node in overview.nodes
        }
        for edge in overview.edges:
            adjacency.setdefault(edge.source_id, []).append(edge)
            adjacency.setdefault(edge.target_id, []).append(edge)
        frozen = {nid: tuple(edges) for nid, edges in adjacency.items()}
        max_degree = max((len(edges) for edges in frozen.values()), default=0)
        return cls(_adjacency=frozen, _max_degree=max_degree)

    def edges_for(self, node_id: str) -> list[GraphEdge]:
        """All edges incident to ``node_id`` (both directions), or ``[]``."""
        return list(self._adjacency.get(node_id, ()))

    def degree(self, node_id: str) -> int:
        """Number of edges incident to ``node_id`` (0 if absent/isolated)."""
        return len(self._adjacency.get(node_id, ()))

    def is_isolated(self, node_id: str) -> bool:
        """True when ``node_id`` has no incident edges."""
        return self.degree(node_id) == 0

    @property
    def max_degree(self) -> int:
        """Highest degree in the snapshot — the centrality normalizer."""
        return self._max_degree


class GraphSnapshotProvider:
    """Builds a :class:`GraphSnapshot` from one batched subgraph read."""

    def __init__(self, graph_repo: GraphRepository) -> None:
        self._graph = graph_repo

    async def snapshot(self, user_id: UUID) -> GraphSnapshot:
        overview = await self._graph.get_subgraph(user_id)
        return GraphSnapshot.from_overview(overview)

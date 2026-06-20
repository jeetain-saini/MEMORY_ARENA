"""GraphSyncService — keep the knowledge graph in sync with memories.

On create/update it upserts the memory's node and **re-derives** its edges: the
node's existing edges are removed first, then freshly derived edges are written,
so an update can never leave a stale edge behind. On delete it removes the node
(and, in every backend, its incident edges). Driven by domain events via a
background job processor — never called directly by use cases.

To keep a single write O(K) rather than O(N) in a user's memory count, edges are
derived against a *bounded* candidate set (the most recent
``GraphConfig.max_sync_candidates`` memories) rather than the whole corpus.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.dto.graph_dto import GraphEdgeType
from app.application.interfaces.graph_job_processor import GraphSyncAction, GraphSyncJob
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.graph.config import GraphConfig
from app.application.services.graph.mapping import memory_to_node
from app.application.services.graph.relationship_service import GraphRelationshipService


class GraphSyncService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        repository: GraphRepository,
        relationship_service: GraphRelationshipService,
        config: GraphConfig | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._repo = repository
        self._relationships = relationship_service
        self._config = config or GraphConfig()

    # -- job API (used by the background processor) ------------------------
    async def process(self, job: GraphSyncJob) -> None:
        if job.action is GraphSyncAction.REMOVE:
            await self.remove_memory(job.memory_id)
        else:
            await self.sync_memory(job.memory_id)

    async def sync_memory(self, memory_id: UUID) -> None:
        async with self._uow_factory() as uow:
            memory = await uow.memories.get_by_id(memory_id)
            if memory is None:
                return
            others = await uow.memories.list_by_user(
                memory.user_id, limit=self._config.max_sync_candidates
            )

        node = memory_to_node(memory)
        await self._repo.upsert_node(node)

        # Re-derive: drop this node's existing edges so an update never leaves a
        # stale edge behind, then write the freshly derived ones.
        # Externally-managed edge types (e.g. CONTRADICTS from consolidation) are
        # excluded — they are not re-derived here and must not be deleted.
        _SYNC_EXCLUDE = frozenset({GraphEdgeType.CONTRADICTS})
        for existing in await self._repo.get_edges(node.node_id, exclude_types=_SYNC_EXCLUDE):
            await self._repo.delete_edge(
                existing.source_id, existing.target_id, existing.edge_type
            )

        candidates = [memory_to_node(m) for m in others if m.id != memory.id]
        by_id = {c.node_id: c for c in candidates}
        for edge in self._relationships.derive_edges(node, candidates):
            # Ensure both endpoints exist so traversal can resolve them.
            for endpoint_id in (edge.source_id, edge.target_id):
                if endpoint_id in by_id:
                    await self._repo.upsert_node(by_id[endpoint_id])
            await self._repo.create_edge(edge)

    async def remove_memory(self, memory_id: UUID) -> None:
        await self._repo.delete_node(str(memory_id))

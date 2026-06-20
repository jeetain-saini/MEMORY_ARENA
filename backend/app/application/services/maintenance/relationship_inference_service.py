"""RelationshipInferenceService — infer & persist graph edges (Stage 11 Phase B).

When a memory is created, this service compares it against a bounded set of the
user's recent memories, infers likely relationships lexically (no LLM), and
writes graph edges for those above a confidence threshold — through the existing
``GraphRepository``.

Three properties make it safe alongside ``GraphSyncService``:

* **Confidence threshold** — only edges with confidence ≥ the configured
  threshold are written.
* **Duplicate-edge prevention** — existing incident edges are read first; an edge
  is skipped if one of the same type already connects the pair (either
  direction), so re-running never duplicates and inference never duplicates a
  sync-derived edge.
* **Graph-sync compatibility** — the semantic edge types (DEPENDS_ON,
  DERIVED_FROM, REINFORCES) are in ``GraphConfig.externally_managed_edge_types``,
  so ``GraphSyncService`` re-derivation preserves them. RELATED_TO remains
  sync-owned; inference only adds one when none exists.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.dto.graph_dto import GraphEdge
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.maintenance_job_processor import InferenceJob
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.graph.config import GraphConfig
from app.application.services.graph.mapping import memory_to_node
from app.application.services.maintenance.config import MaintenanceConfig
from app.application.services.maintenance.inference_heuristics import infer_relationship
from app.domain.value_objects.memory_status import MemoryStatus


class RelationshipInferenceService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        graph_repo: GraphRepository,
        config: MaintenanceConfig | None = None,
        graph_config: GraphConfig | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._repo = graph_repo
        self._config = config or MaintenanceConfig()
        self._graph_config = graph_config or GraphConfig()

    async def process(self, job: InferenceJob) -> None:
        await self.infer_for_memory(job.memory_id)

    async def infer_for_memory(self, memory_id: UUID) -> int:
        """Infer relationships for ``memory_id``; return the number of edges written."""
        async with self._uow_factory() as uow:
            memory = await uow.memories.get_by_id(memory_id)
            if memory is None or memory.status is not MemoryStatus.ACTIVE:
                return 0
            candidates = await uow.memories.list_by_user(
                memory.user_id, limit=self._config.inference_candidate_pool
            )

        source_node = memory_to_node(memory)
        await self._repo.upsert_node(source_node)

        # Dedup key: undirected pair + edge type, seeded from existing edges.
        existing = await self._repo.get_edges(source_node.node_id)
        seen: set[tuple[frozenset[str], str]] = {
            (frozenset({edge.source_id, edge.target_id}), edge.edge_type.value)
            for edge in existing
        }

        threshold = self._config.inference_confidence_threshold
        created = 0
        for candidate in candidates:
            if candidate.id == memory.id or candidate.status is not MemoryStatus.ACTIVE:
                continue
            relationship = infer_relationship(
                source_content=memory.content,
                source_type=memory.memory_type,
                target_content=candidate.content,
                target_type=candidate.memory_type,
                min_entity_length=self._graph_config.min_entity_length,
            )
            if relationship is None or relationship.confidence < threshold:
                continue

            target_node = memory_to_node(candidate)
            key = (
                frozenset({source_node.node_id, target_node.node_id}),
                relationship.edge_type.value,
            )
            if key in seen:
                continue
            seen.add(key)

            await self._repo.upsert_node(target_node)
            await self._repo.create_edge(
                GraphEdge(
                    source_id=source_node.node_id,
                    target_id=target_node.node_id,
                    edge_type=relationship.edge_type,
                    weight=relationship.confidence,
                    properties={"confidence": relationship.confidence, "inferred": True},
                )
            )
            created += 1
        return created

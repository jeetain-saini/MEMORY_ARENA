"""ContradictionResolutionService — resolve a CONTRADICTS pair (Stage 16).

Given an authoritative memory to keep and an obsolete one to archive, it:
  1. archives the obsolete memory (ACTIVE -> ARCHIVED, recording MemoryArchived so
     the graph node re-statuses via the existing sync handler),
  2. preserves the CONTRADICTS edge between them as history (never deleted),
  3. writes a durable SUPERSEDES edge: kept -> archived.

It does not touch the contradiction-detection or consolidation pipelines; it only
acts on an already-detected (or user-asserted) contradiction. SUPERSEDES is in the
graph-sync externally-managed set, so re-derivation never deletes it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.application.dto.auth_dto import AuthPrincipal
from app.application.dto.graph_dto import GraphEdge, GraphEdgeType
from app.application.dto.resolution_dto import ContradictionResolutionResult
from app.application.exceptions import MemoryNotFoundException, MemoryValidationException
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.presenters import memory_to_response
from app.application.services.authorization import authorize_owner
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus


class ContradictionResolutionService:
    def __init__(
        self,
        uow: UnitOfWork,
        graph_repo: GraphRepository,
        dispatcher: EventDispatcher,
        principal: AuthPrincipal | None = None,
    ) -> None:
        self._uow = uow
        self._graph = graph_repo
        self._dispatcher = dispatcher
        self._principal = principal

    async def resolve(
        self,
        *,
        keep_id: UUID,
        archive_id: UUID,
        user_id: UUID | None = None,
    ) -> ContradictionResolutionResult:
        if keep_id == archive_id:
            raise MemoryValidationException("keep_id and archive_id must differ.")

        async with self._uow as uow:
            kept = await self._require(uow, keep_id, user_id)
            obsolete = await self._require(uow, archive_id, user_id)
            if obsolete.status == MemoryStatus.ACTIVE:
                obsolete.archive()  # records MemoryArchived -> graph node re-status
                await uow.memories.update(obsolete)
            await uow.commit()
            kept_resp = memory_to_response(kept)
            obsolete_resp = memory_to_response(obsolete)

        # Post-commit: graph node re-status for the archived memory (if any event).
        await self._dispatcher.dispatch(obsolete.pull_events())

        # Was there a CONTRADICTS edge? It is preserved (never deleted) as history.
        edges = await self._graph.get_edges(str(keep_id))
        contradiction_preserved = any(
            e.edge_type == GraphEdgeType.CONTRADICTS
            and {e.source_id, e.target_id} == {str(keep_id), str(archive_id)}
            for e in edges
        )

        # Durable SUPERSEDES edge: kept -> archived (excluded from sync re-derivation).
        await self._graph.create_edge(
            GraphEdge(
                source_id=str(keep_id),
                target_id=str(archive_id),
                edge_type=GraphEdgeType.SUPERSEDES,
                weight=1.0,
                properties={
                    "reason": "contradiction_resolution",
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        )
        return ContradictionResolutionResult(
            kept=kept_resp,
            archived=obsolete_resp,
            superseded_edge=True,
            contradiction_preserved=contradiction_preserved,
        )

    async def _require(self, uow: UnitOfWork, memory_id: UUID, user_id: UUID | None) -> Memory:
        memory = await uow.memories.get_by_id(memory_id)
        if memory is None or (user_id is not None and memory.user_id != user_id):
            raise MemoryNotFoundException(memory_id)
        if self._principal is not None:
            authorize_owner(self._principal, memory.user_id)
        return memory

"""PersistentConsolidationService — write-time memory consolidation.

Driven by background jobs (one per MemoryCreated event).  For each job:
  1. Load the new memory and a bounded pool of ACTIVE candidate memories.
  2. Ask the ConsolidationEngine to compare them.
  3. Act on SUPERSEDES decisions (archive the older memory).
  4. Act on CONTRADICTS decisions (write a durable CONTRADICTS graph edge).
  5. MERGE decisions are recorded in the summary only (no action in Phase 2).

All domain types are accessed through ports; no framework imports here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from app.application.dto.consolidation_dto import (
    ConsolidationCandidate,
    ConsolidationDecision,
    ConsolidationDecisionType,
    ConsolidationRequest,
    ConsolidationSummary,
)
from app.application.dto.graph_dto import GraphEdge, GraphEdgeType
from app.application.interfaces.consolidation_engine import ConsolidationEngine
from app.application.interfaces.consolidation_job_processor import ConsolidationJob
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.consolidation.config import ConsolidationConfig
from app.domain.entities.memory import Memory
from app.domain.events.memory_events import MemoryConflictFound, MemorySuperseded
from app.domain.value_objects.memory_status import MemoryStatus

_logger = logging.getLogger("memoryarena.consolidation")


class PersistentConsolidationService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        engine: ConsolidationEngine,
        intelligence_service_factory: Callable,
        graph_repo: GraphRepository,
        dispatcher: EventDispatcher,
        config: ConsolidationConfig | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._engine = engine
        self._intelligence_service_factory = intelligence_service_factory
        self._graph_repo = graph_repo
        self._dispatcher = dispatcher
        self._config = config or ConsolidationConfig()

    async def process(self, job: ConsolidationJob) -> ConsolidationSummary:
        new_memory, candidates = await self._load(job.memory_id, job.user_id)

        if new_memory is None:
            _logger.info(
                "consolidation.job.memory_not_found",
                extra={"memory_id": str(job.memory_id)},
            )
            return ConsolidationSummary(
                new_memory_id=job.memory_id,
                user_id=job.user_id,
                total_candidates=0,
                decisions=[],
                workflow_version=self._config.workflow_version,
            )

        request = ConsolidationRequest(
            new_memory_id=new_memory.id,
            user_id=new_memory.user_id,
            new_content=new_memory.content,
            new_type=new_memory.memory_type,
            candidates=candidates,
        )

        decisions = await self._engine.consolidate(request)

        _logger.info(
            "consolidation.job.decisions",
            extra={
                "memory_id": str(job.memory_id),
                "candidates": len(candidates),
                "decisions": len(decisions),
            },
        )

        await self._apply(job, decisions)

        return ConsolidationSummary(
            new_memory_id=job.memory_id,
            user_id=job.user_id,
            total_candidates=len(candidates),
            decisions=decisions,
            workflow_version=self._config.workflow_version,
        )

    # -- internals -----------------------------------------------------------

    async def _load(
        self, memory_id: UUID, user_id: UUID
    ) -> tuple[Memory | None, list[ConsolidationCandidate]]:
        async with self._uow_factory() as uow:
            new_memory = await uow.memories.get_by_id(memory_id)
            if new_memory is None:
                return None, []

            all_memories = await uow.memories.list_by_user(
                user_id, limit=self._config.candidate_pool + 1
            )

        candidates = [
            ConsolidationCandidate(
                memory_id=m.id,
                content=m.content,
                memory_type=m.memory_type,
                total_score=m.total_score,
                updated_at=m.updated_at,
            )
            for m in all_memories
            if m.id != memory_id and m.status == MemoryStatus.ACTIVE
        ]
        return new_memory, candidates

    async def _apply(
        self, job: ConsolidationJob, decisions: list[ConsolidationDecision]
    ) -> None:
        for decision in decisions:
            if decision.decision_type == ConsolidationDecisionType.SUPERSEDES:
                await self._apply_supersedes(job, decision)
            elif decision.decision_type == ConsolidationDecisionType.CONTRADICTS:
                await self._apply_contradicts(job, decision)
            # UNIQUE and MERGE: no action in Phase 2

    async def _apply_supersedes(
        self, job: ConsolidationJob, decision: ConsolidationDecision
    ) -> None:
        if decision.confidence < self._config.supersede_confidence:
            _logger.debug(
                "consolidation.supersedes.below_threshold",
                extra={
                    "target_id": str(decision.target_id),
                    "confidence": decision.confidence,
                    "threshold": self._config.supersede_confidence,
                },
            )
            return

        assert decision.target_id is not None
        try:
            intelligence = self._intelligence_service_factory()
            await intelligence.archive_memory(decision.target_id, force=True)
        except Exception:
            _logger.exception(
                "consolidation.supersedes.archive_failed",
                extra={"target_id": str(decision.target_id)},
            )
            return

        await self._dispatcher.dispatch(
            [
                MemorySuperseded(
                    memory_id=decision.target_id,
                    superseded_by_id=job.memory_id,
                    user_id=job.user_id,
                )
            ]
        )
        _logger.info(
            "consolidation.supersedes.archived",
            extra={"target_id": str(decision.target_id), "new_id": str(job.memory_id)},
        )

    async def _apply_contradicts(
        self, job: ConsolidationJob, decision: ConsolidationDecision
    ) -> None:
        if decision.confidence < self._config.contradict_confidence:
            _logger.debug(
                "consolidation.contradicts.below_threshold",
                extra={
                    "target_id": str(decision.target_id),
                    "confidence": decision.confidence,
                    "threshold": self._config.contradict_confidence,
                },
            )
            return

        assert decision.target_id is not None
        edge = GraphEdge(
            source_id=str(job.memory_id),
            target_id=str(decision.target_id),
            edge_type=GraphEdgeType.CONTRADICTS,
            weight=decision.confidence,
            properties={
                "reasoning": decision.reasoning,
                "workflow_version": self._config.workflow_version,
            },
        )
        await self._graph_repo.create_edge(edge)

        await self._dispatcher.dispatch(
            [
                MemoryConflictFound(
                    memory_id_a=job.memory_id,
                    memory_id_b=decision.target_id,
                    user_id=job.user_id,
                    reasoning=decision.reasoning,
                )
            ]
        )
        _logger.info(
            "consolidation.contradicts.edge_written",
            extra={
                "memory_id_a": str(job.memory_id),
                "memory_id_b": str(decision.target_id),
            },
        )

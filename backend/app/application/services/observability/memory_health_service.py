"""MemoryHealthService — evolving-corpus metrics for a tenant (Stage 13).

Aggregates read-only signals over a user's memories, rolling summaries, and
knowledge-graph density. It introduces no new write path and no counters: every
metric is derived from data the system already stores. Where a true metric would
require event-level counting that does not yet exist (retrieval frequency,
reinforcement frequency), it reports an honest proxy and records the caveat in
``notes`` — the real counters are deferred to Stage 14.

Like ``MemoryAnalyticsService`` it loads memories and aggregates in Python,
which is fine at current scale; SQL-side aggregation is a future optimization.
``now`` is injectable so growth windows are deterministic in tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.application.dto.health_dto import MemoryHealth
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.unit_of_work import UnitOfWork
from app.domain.entities.memory import Memory
from app.domain.entities.memory_summary import MemorySummary
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType

# Scopes for which the Stage 11 workflow maintains rolling summaries.
_SUMMARY_SCOPES: tuple[MemoryType, ...] = (
    MemoryType.PROJECT,
    MemoryType.GOAL,
    MemoryType.EXPERIENCE,
)

_NOTES = {
    "retrieval_frequency": "not tracked; requires a retrieval counter (deferred to Stage 14)",
    "reinforcement_frequency": (
        "proxy: avg_reinforcement_signal is the mean frequency score over active "
        "memories; event-level counts are deferred to Stage 14"
    ),
    "graph_density": "edges per node among the tenant's graph nodes",
}


class MemoryHealthService:
    def __init__(self, uow: UnitOfWork, graph_repository: GraphRepository) -> None:
        self._uow = uow
        self._graph = graph_repository

    async def get_health(
        self, user_id: UUID | None = None, *, now: datetime | None = None
    ) -> MemoryHealth:
        now = now or datetime.now(timezone.utc)
        async with self._uow as uow:
            memories = await uow.memories.list_for_analytics(user_id)
            summaries = await uow.summaries.list_for_user(user_id) if user_id is not None else []
        nodes = await self._graph.count_nodes(user_id)
        edges = await self._graph.count_edges(user_id)
        return self._aggregate(memories, summaries, nodes, edges, user_id, now)

    def _aggregate(
        self,
        memories: list[Memory],
        summaries: list[MemorySummary],
        graph_nodes: int,
        graph_edges: int,
        user_id: UUID | None,
        now: datetime,
    ) -> MemoryHealth:
        total = len(memories)
        active = [m for m in memories if m.status is MemoryStatus.ACTIVE]
        archived = sum(1 for m in memories if m.status is MemoryStatus.ARCHIVED)
        promoted = sum(1 for m in memories if m.is_promoted)

        scores = [m.total_score for m in memories]
        average_score = round(sum(scores) / len(scores), 4) if scores else 0.0
        freqs = [m.score.frequency for m in active]
        avg_reinforcement = round(sum(freqs) / len(freqs), 4) if freqs else 0.0

        cutoff_7 = now - timedelta(days=7)
        cutoff_30 = now - timedelta(days=30)
        created_7 = sum(1 for m in memories if m.created_at >= cutoff_7)
        created_30 = sum(1 for m in memories if m.created_at >= cutoff_30)

        density = round(graph_edges / graph_nodes, 4) if graph_nodes else 0.0

        expected, present, coverage = self._summary_coverage(active, summaries, user_id)

        return MemoryHealth(
            user_id=user_id,
            total_memories=total,
            active_memories=len(active),
            archived_memories=archived,
            promoted_memories=promoted,
            promotion_rate=round(promoted / total, 4) if total else 0.0,
            archive_rate=round(archived / total, 4) if total else 0.0,
            created_last_7_days=created_7,
            created_last_30_days=created_30,
            average_score=average_score,
            avg_reinforcement_signal=avg_reinforcement,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            graph_density=density,
            summary_scopes_expected=expected,
            summary_scopes_present=present,
            summary_coverage=coverage,
            notes=dict(_NOTES),
        )

    @staticmethod
    def _summary_coverage(
        active: list[Memory], summaries: list[MemorySummary], user_id: UUID | None
    ) -> tuple[int, int, float]:
        # Coverage is only meaningful per-tenant (summaries are per user_id).
        if user_id is None:
            return 0, 0, 1.0
        present_scopes = {s.scope for s in summaries}
        active_scopes = {m.memory_type for m in active}
        expected_scopes = [sc for sc in _SUMMARY_SCOPES if sc in active_scopes]
        expected = len(expected_scopes)
        present = sum(1 for sc in expected_scopes if sc in present_scopes)
        coverage = round(present / expected, 4) if expected else 1.0
        return expected, present, coverage

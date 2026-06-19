"""MemoryAnalyticsService — aggregate statistics over a user's memories.

Reads non-deleted memories through the Unit of Work and computes counts, the
average total score, and a score distribution. Total scores are computed by the
domain (``MemoryScore.calculate_total_score``), keeping the weighting authoritative
in one place.

Note: this loads memories to aggregate in Python, which is fine at current scale;
a future optimization is SQL-side aggregation for very large tenants.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.analytics_dto import MemoryAnalytics
from app.application.interfaces.unit_of_work import UnitOfWork
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus

# Score buckets, lower-bound inclusive; the last bucket includes 1.0.
_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0.0-0.2", 0.0, 0.2),
    ("0.2-0.4", 0.2, 0.4),
    ("0.4-0.6", 0.4, 0.6),
    ("0.6-0.8", 0.6, 0.8),
    ("0.8-1.0", 0.8, 1.0001),
)


class MemoryAnalyticsService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def get_analytics(self, user_id: UUID | None = None) -> MemoryAnalytics:
        async with self._uow as uow:
            memories = await uow.memories.list_for_analytics(user_id)
        return self._aggregate(memories)

    def _aggregate(self, memories: list[Memory]) -> MemoryAnalytics:
        active = sum(1 for m in memories if m.status is MemoryStatus.ACTIVE)
        archived = sum(1 for m in memories if m.status is MemoryStatus.ARCHIVED)
        promoted = sum(1 for m in memories if m.is_promoted)

        scores = [m.total_score for m in memories]
        average = round(sum(scores) / len(scores), 4) if scores else 0.0

        distribution = {label: 0 for label, _, _ in _BUCKETS}
        for score in scores:
            for label, low, high in _BUCKETS:
                if low <= score < high:
                    distribution[label] += 1
                    break

        return MemoryAnalytics(
            total_memories=len(memories),
            active_memories=active,
            archived_memories=archived,
            promoted_memories=promoted,
            average_score=average,
            score_distribution=distribution,
        )

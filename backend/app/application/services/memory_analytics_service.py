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
from app.application.dto.auth_dto import AuthPrincipal
from app.application.interfaces.cache_provider import CacheProvider
from app.application.interfaces.metrics_sink import MetricsSink
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.authorization import resolve_scope
from app.application.services.cache.cache_keys import analytics_key
from app.application.services.cache.serialization import dump_analytics, load_analytics
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
    def __init__(
        self,
        uow: UnitOfWork,
        principal: AuthPrincipal | None = None,
        cache: CacheProvider | None = None,
        metrics: MetricsSink | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self._uow = uow
        self._principal = principal
        self._cache = cache
        self._metrics = metrics
        self._ttl = cache_ttl_seconds

    async def get_analytics(self, user_id: UUID | None = None) -> MemoryAnalytics:
        # Authorize first so the cache key is the *effective* (post-scope) user —
        # a caller can never read another user's cached aggregate.
        user_id = resolve_scope(self._principal, user_id)
        key = analytics_key(user_id)

        if self._cache is not None:
            cached = await self._cache.get(key)
            if cached is not None:
                self._record("cache.hit.analytics")
                return load_analytics(cached)
            self._record("cache.miss.analytics")

        async with self._uow as uow:
            memories = await uow.memories.list_for_analytics(user_id)
        result = self._aggregate(memories)

        if self._cache is not None:
            await self._cache.set(key, dump_analytics(result), ttl_seconds=self._ttl)
        return result

    def _record(self, name: str) -> None:
        if self._metrics is not None:
            self._metrics.incr(name)

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

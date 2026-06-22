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

from app.application.dto.auth_dto import AuthPrincipal
from app.application.dto.health_dto import MemoryHealth
from app.application.interfaces.cache_provider import CacheProvider
from app.application.dto.graph_dto import GraphEdgeType
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.metrics_sink import MetricsSink
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.authorization import resolve_scope
from app.application.services.cache.cache_keys import health_key
from app.application.services.cache.serialization import dump_health, load_health
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

def _bucket(values) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Bucket [0,1] values into 5 ranges for a distribution histogram."""
    labels = ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
    out = {lbl: 0 for lbl in labels}
    for v in values:
        idx = min(4, int(max(0.0, min(1.0, v)) * 5))
        out[labels[idx]] += 1
    return out


_NOTES = {
    "retrieval_frequency": "not tracked; requires a retrieval counter (deferred to Stage 14)",
    "reinforcement_frequency": (
        "proxy: avg_reinforcement_signal is the mean frequency score over active "
        "memories; event-level counts are deferred to Stage 14"
    ),
    "graph_density": "edges per node among the tenant's graph nodes",
}


class MemoryHealthService:
    def __init__(
        self,
        uow: UnitOfWork,
        graph_repository: GraphRepository,
        principal: AuthPrincipal | None = None,
        cache: CacheProvider | None = None,
        metrics: MetricsSink | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self._uow = uow
        self._graph = graph_repository
        self._principal = principal
        self._cache = cache
        self._metrics = metrics
        self._ttl = cache_ttl_seconds

    async def get_health(
        self, user_id: UUID | None = None, *, now: datetime | None = None
    ) -> MemoryHealth:
        user_id = resolve_scope(self._principal, user_id)
        key = health_key(user_id)

        # Cache only the wall-clock-default path; a caller-supplied ``now`` is a
        # test/deterministic override and must not read or pollute the cache.
        use_cache = self._cache is not None and now is None
        if use_cache:
            cached = await self._cache.get(key)
            if cached is not None:
                self._record("cache.hit.health")
                return load_health(cached)
            self._record("cache.miss.health")

        now = now or datetime.now(timezone.utc)
        async with self._uow as uow:
            memories = await uow.memories.list_for_analytics(user_id)
            summaries = await uow.summaries.list_for_user(user_id) if user_id is not None else []
        nodes = await self._graph.count_nodes(user_id)
        edges = await self._graph.count_edges(user_id)
        # Contradiction / supersession counts come from the tenant's subgraph
        # (per-user only; the global view skips per-type edge counts).
        contradictions = superseded = promoted_from = 0
        cluster_ids: set[str] = set()
        if user_id is not None:
            overview = await self._graph.get_subgraph(user_id)
            for e in overview.edges:
                if e.edge_type is GraphEdgeType.CONTRADICTS:
                    contradictions += 1
                elif e.edge_type is GraphEdgeType.SUPERSEDES:
                    superseded += 1
                elif e.edge_type is GraphEdgeType.PROMOTED_FROM:
                    promoted_from += 1
                elif e.edge_type is GraphEdgeType.CLUSTER_MEMBER:
                    cid = e.properties.get("cluster_id")
                    if cid:
                        cluster_ids.add(str(cid))
        result = self._aggregate(
            memories, summaries, nodes, edges, contradictions, superseded,
            promoted_from, len(cluster_ids), user_id, now,
        )

        if use_cache:
            await self._cache.set(key, dump_health(result), ttl_seconds=self._ttl)
        return result

    def _record(self, name: str) -> None:
        if self._metrics is not None:
            self._metrics.incr(name)

    def _aggregate(
        self,
        memories: list[Memory],
        summaries: list[MemorySummary],
        graph_nodes: int,
        graph_edges: int,
        contradiction_count: int,
        superseded_count: int,
        promoted_from_count: int,
        cluster_count: int,
        user_id: UUID | None,
        now: datetime,
    ) -> MemoryHealth:
        from app.domain.value_objects.memory_category import MemoryCategory

        total = len(memories)
        active = [m for m in memories if m.status is MemoryStatus.ACTIVE]
        archived = sum(1 for m in memories if m.status is MemoryStatus.ARCHIVED)
        forgotten = sum(1 for m in memories if m.status is MemoryStatus.FORGOTTEN)
        promoted = sum(1 for m in memories if m.is_promoted)
        episodic = sum(1 for m in memories if m.category is MemoryCategory.EPISODIC)
        semantic = sum(1 for m in memories if m.category is MemoryCategory.SEMANTIC)

        scores = [m.total_score for m in memories]
        average_score = round(sum(scores) / len(scores), 4) if scores else 0.0
        freqs = [m.score.frequency for m in active]
        avg_reinforcement = round(sum(freqs) / len(freqs), 4) if freqs else 0.0

        # composition + quality (Stage 16)
        type_distribution: dict[str, int] = {}
        for m in memories:
            key = m.memory_type.value
            type_distribution[key] = type_distribution.get(key, 0) + 1
        importances = [m.score.importance for m in memories]
        confidences = [m.score.confidence for m in memories]
        avg_importance = round(sum(importances) / len(importances), 4) if importances else 0.0
        avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

        cutoff_7 = now - timedelta(days=7)
        cutoff_30 = now - timedelta(days=30)
        # Coerce naive timestamps (e.g. round-tripped through SQLite) to UTC so the
        # comparison never mixes naive/aware datetimes — mirrors the defensive
        # normalization in MemoryIntelligenceService._should_archive.
        created_at = [
            m.created_at if m.created_at.tzinfo else m.created_at.replace(tzinfo=timezone.utc)
            for m in memories
        ]
        created_7 = sum(1 for ts in created_at if ts >= cutoff_7)
        created_30 = sum(1 for ts in created_at if ts >= cutoff_30)

        density = round(graph_edges / graph_nodes, 4) if graph_nodes else 0.0

        # Stage 17: age, retrieval-frequency stats, importance/confidence buckets.
        ages = [(now - ts).total_seconds() / 86400.0 for ts in created_at]
        avg_age = round(sum(ages) / len(ages), 4) if ages else 0.0
        rcounts = [m.retrieval_count for m in memories]
        retrieval_stats = {
            "total": float(sum(rcounts)),
            "average": round(sum(rcounts) / len(rcounts), 4) if rcounts else 0.0,
            "max": float(max(rcounts)) if rcounts else 0.0,
        }
        importance_dist = _bucket(m.score.importance for m in memories)
        confidence_dist = _bucket(m.score.confidence for m in memories)

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
            contradiction_count=contradiction_count,
            superseded_count=superseded_count,
            type_distribution=type_distribution,
            average_importance=avg_importance,
            average_confidence=avg_confidence,
            forgotten_count=forgotten,
            episodic_count=episodic,
            semantic_count=semantic,
            cluster_count=cluster_count,
            promoted_from_count=promoted_from_count,
            average_memory_age_days=avg_age,
            retrieval_frequency_stats=retrieval_stats,
            importance_distribution=importance_dist,
            confidence_distribution=confidence_dist,
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

"""MemoryIntelligenceMaintenanceJob — the autonomous Stage 17.1 driver.

A single ``ScheduledJob`` that runs the full self-evolving cycle for every
tenant, in dependency order::

    importance evolution -> promotion -> clustering -> forgetting

It owns no evolution logic; it orchestrates the existing Stage 17 engines and
the ``ImportanceEvolutionService``, mirroring the Stage 11 maintenance sweeps
(tenant-aware, idempotent, resumable). Registered on the in-process scheduler in
the composition root and fired on its cron by the scheduler's driver/ticker —
the same mechanism as ``DecaySweepJob``/``PromotionSweepJob``. The
``/intelligence/*`` endpoints keep calling the same engines, so they remain
manual overrides of this automatic path.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from uuid import UUID

from app.application.interfaces.distributed_lock import DistributedLock
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.metrics_sink import MetricsSink
from app.application.interfaces.scheduler import ScheduledJob
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.concurrency import bounded_gather, chunked
from app.application.services.intelligence.clustering_engine import ClusteringEngine
from app.application.services.locking import LockLease, single_owner
from app.application.services.intelligence.forgetting_engine import ForgettingEngine
from app.application.services.intelligence.graph_snapshot import (
    GraphSnapshot,
    GraphSnapshotProvider,
)
from app.application.services.intelligence.importance_evolution import (
    ImportanceEvolutionService,
)
from app.application.services.intelligence.promotion_engine import PromotionEngine
from app.domain.value_objects.memory_status import MemoryStatus

UowFactory = Callable[[], UnitOfWork]

_logger = logging.getLogger("memoryarena.intelligence")


async def evolve_importance_for_user(
    uow_factory: UowFactory,
    graph_repo: GraphRepository,
    evolution: ImportanceEvolutionService,
    user_id: UUID,
    *,
    snapshot: GraphSnapshot | None = None,
) -> int:
    """Recompute + persist importance for a user's active memories.

    Graph-aware: centrality is ``degree / max-degree`` across the active set, so
    well-connected memories evolve upward. Returns the number of memories whose
    importance actually changed (idempotent — a no-op when nothing moves).

    Stage 18.1: degrees come from a single batched :class:`GraphSnapshot` when
    one is supplied; otherwise the function builds one itself (one ``get_subgraph``
    call) instead of issuing one ``get_edges`` per memory.
    """
    async with uow_factory() as uow:
        memories = [
            m
            for m in await uow.memories.list_for_analytics(user_id)
            if m.status is MemoryStatus.ACTIVE
        ]
    if not memories:
        return 0

    if snapshot is None:
        snapshot = await GraphSnapshotProvider(graph_repo).snapshot(user_id)
    # Normalize centrality over the active set (not the whole subgraph), matching
    # the pre-Stage-18 semantics exactly.
    degrees = {m.id: snapshot.degree(str(m.id)) for m in memories}
    max_degree = max(degrees.values(), default=0)

    changed = 0
    async with uow_factory() as uow:
        for m in memories:
            centrality = (degrees[m.id] / max_degree) if max_degree else 0.0
            new_score = evolution.evolve(m, centrality=centrality)
            if new_score.importance != m.score.importance:
                m.score = new_score
                await uow.memories.update(m)
                changed += 1
        await uow.commit()
    return changed


@dataclass(frozen=True)
class IntelligenceMaintenanceResult:
    tenants: int
    importance_changed: int
    promoted: int
    clustered: int
    forgotten: int


class MemoryIntelligenceMaintenanceJob(ScheduledJob):
    """Runs importance evolution, promotion, clustering, and forgetting."""

    name = "memory_intelligence_maintenance"

    def __init__(
        self,
        uow_factory: UowFactory,
        graph_repo: GraphRepository,
        dispatcher: EventDispatcher,
        *,
        evolution: ImportanceEvolutionService | None = None,
        promotion: PromotionEngine | None = None,
        forgetting: ForgettingEngine | None = None,
        clustering: ClusteringEngine | None = None,
        metrics: MetricsSink | None = None,
        lock: DistributedLock | None = None,
        lock_key: str = "intelligence:maintenance",
        lock_ttl_seconds: int = 300,
        max_concurrency: int = 1,
    ) -> None:
        self._uow_factory = uow_factory
        self._graph = graph_repo
        self._snapshots = GraphSnapshotProvider(graph_repo)
        self._metrics = metrics
        self._lock = lock
        self._lock_key = lock_key
        self._lock_ttl = lock_ttl_seconds
        self._max_concurrency = max(1, max_concurrency)
        self._evolution = evolution or ImportanceEvolutionService()
        self._promotion = promotion or PromotionEngine(uow_factory, graph_repo, dispatcher)
        self._forgetting = forgetting or ForgettingEngine(uow_factory, graph_repo, dispatcher)
        self._clustering = clustering or ClusteringEngine(
            uow_factory, graph_repo, metrics=metrics
        )

    async def run(self) -> None:
        """Scheduler entry point — runs one all-tenant cycle under the lock.

        Stage 18.3: when a distributed lock is configured, the cycle runs only on
        the single instance that holds ``lock_key``; other instances skip this
        tick. The lease is renewed between tenants so a long cycle keeps ownership,
        and is released on exit (a crashed owner's lease lapses on its TTL). With
        no lock configured the behavior is unchanged (single-process default).
        """
        if self._lock is None:
            await self.run_cycle()
            return
        async with single_owner(
            self._lock, self._lock_key, ttl_seconds=self._lock_ttl
        ) as lease:
            if lease is None:
                _logger.info("intelligence.maintenance.skipped_lock_held")
                if self._metrics is not None:
                    self._metrics.incr("intelligence_maintenance_skipped_total")
                return
            await self.run_cycle(lease=lease)

    def _tenant_factory(
        self, uid: UUID
    ) -> Callable[[], Awaitable[tuple[int, int, int, int]]]:
        # Bind uid now so bounded_gather can start each tenant lazily (no late
        # binding across the chunk).
        return lambda: self._run_tenant(uid)

    async def _run_tenant(self, uid: UUID) -> tuple[int, int, int, int]:
        """Run the full evolution cycle for a single tenant; return its counts.

        Order matters: evolve importance first (forgetting reads it), then promote
        (creates semantic memories), cluster (includes the new semantic ones), and
        finally forget (protect_promoted keeps the freshly promoted ones).

        Stage 18.1: one batched subgraph read feeds importance evolution (which
        runs before any graph mutation). Promotion and clustering then add edges,
        so forgetting takes a *fresh* snapshot to see the updated topology — two
        get_subgraph calls per tenant in place of the previous O(N) per-memory
        get_edges reads.
        """
        pre_snapshot = await self._snapshots.snapshot(uid)
        importance = await evolve_importance_for_user(
            self._uow_factory, self._graph, self._evolution, uid, snapshot=pre_snapshot
        )
        promoted = len(await self._promotion.promote_user(uid))
        clustered = len(await self._clustering.cluster_user(uid))
        post_snapshot = await self._snapshots.snapshot(uid)
        forgotten = len(await self._forgetting.sweep_user(uid, snapshot=post_snapshot))
        return importance, promoted, clustered, forgotten

    async def run_cycle(
        self, *, user_id: UUID | None = None, lease: LockLease | None = None
    ) -> IntelligenceMaintenanceResult:
        """Run one full evolution cycle for one tenant (or all tenants).

        Stage 18.4: tenants are processed in chunks of ``max_concurrency`` with
        ``bounded_gather`` — each tenant uses its own unit of work and disjoint
        rows/graph nodes, so they run safely in parallel up to the ceiling while
        a connection pool bounds the in-flight DB/graph work. ``max_concurrency=1``
        (the default) is ordered sequential execution, identical to pre-18.4. The
        lock lease is renewed between chunks so a long cycle keeps ownership.
        """
        tenants = await self._tenants(user_id)
        importance = promoted = clustered = forgotten = 0
        for chunk in chunked(tenants, self._max_concurrency):
            counts = await bounded_gather(
                [self._tenant_factory(uid) for uid in chunk],
                limit=self._max_concurrency,
            )
            for imp, prom, clus, forg in counts:
                importance += imp
                promoted += prom
                clustered += clus
                forgotten += forg
            # Stage 18.3: keep the lease alive across a long multi-tenant cycle. If
            # ownership was lost (e.g. our lease lapsed and another instance took
            # over), stop rather than keep mutating under a lock we no longer hold.
            if lease is not None and not await lease.renew():
                _logger.warning("intelligence.maintenance.lease_lost")
                break
        result = IntelligenceMaintenanceResult(
            tenants=len(tenants),
            importance_changed=importance,
            promoted=promoted,
            clustered=clustered,
            forgotten=forgotten,
        )
        if self._metrics is not None:
            self._metrics.incr("memories_promoted_total", promoted)
            self._metrics.incr("memories_forgotten_total", forgotten)
            self._metrics.incr("memories_clustered_total", clustered)
            self._metrics.incr("memories_importance_evolved_total", importance)
        _logger.info("intelligence.maintenance", extra=asdict(result))
        return result

    async def _tenants(self, user_id: UUID | None) -> list[UUID]:
        if user_id is not None:
            return [user_id]
        async with self._uow_factory() as uow:
            memories = await uow.memories.list_for_analytics(None)
        ordered: list[UUID] = []
        seen: set[UUID] = set()
        for m in memories:
            if m.user_id not in seen:
                seen.add(m.user_id)
                ordered.append(m.user_id)
        return ordered

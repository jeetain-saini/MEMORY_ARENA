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
from collections.abc import Callable
from dataclasses import asdict, dataclass
from uuid import UUID

from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.scheduler import ScheduledJob
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.intelligence.clustering_engine import ClusteringEngine
from app.application.services.intelligence.forgetting_engine import ForgettingEngine
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
) -> int:
    """Recompute + persist importance for a user's active memories.

    Graph-aware: centrality is ``degree / max-degree`` across the active set, so
    well-connected memories evolve upward. Returns the number of memories whose
    importance actually changed (idempotent — a no-op when nothing moves).
    """
    async with uow_factory() as uow:
        memories = [
            m
            for m in await uow.memories.list_for_analytics(user_id)
            if m.status is MemoryStatus.ACTIVE
        ]
    if not memories:
        return 0

    degrees: dict[UUID, int] = {}
    for m in memories:
        edges = await graph_repo.get_edges(str(m.id))
        degrees[m.id] = len(edges)
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
    ) -> None:
        self._uow_factory = uow_factory
        self._graph = graph_repo
        self._evolution = evolution or ImportanceEvolutionService()
        self._promotion = promotion or PromotionEngine(uow_factory, graph_repo, dispatcher)
        self._forgetting = forgetting or ForgettingEngine(uow_factory, graph_repo, dispatcher)
        self._clustering = clustering or ClusteringEngine(uow_factory, graph_repo)

    async def run(self) -> None:
        await self.run_cycle()

    async def run_cycle(self, *, user_id: UUID | None = None) -> IntelligenceMaintenanceResult:
        """Run one full evolution cycle for one tenant (or all tenants)."""
        tenants = await self._tenants(user_id)
        importance = promoted = clustered = forgotten = 0
        for uid in tenants:
            # Order matters: evolve importance first (forgetting reads it), then
            # promote (creates semantic memories), cluster (includes the new
            # semantic ones), and finally forget (protect_promoted keeps the
            # freshly promoted ones).
            importance += await evolve_importance_for_user(
                self._uow_factory, self._graph, self._evolution, uid
            )
            promoted += len(await self._promotion.promote_user(uid))
            clustered += len(await self._clustering.cluster_user(uid))
            forgotten += len(await self._forgetting.sweep_user(uid))
        result = IntelligenceMaintenanceResult(
            tenants=len(tenants),
            importance_changed=importance,
            promoted=promoted,
            clustered=clustered,
            forgotten=forgotten,
        )
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

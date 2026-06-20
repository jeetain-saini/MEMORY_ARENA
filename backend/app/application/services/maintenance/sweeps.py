"""Scheduled memory-evolution sweeps (Stage 11 Phase A).

Concrete ``ScheduledJob`` implementations that drive memory evolution at scale by
reusing ``MemoryIntelligenceService`` — they contain no new evolution logic.

All three are **tenant-aware** (they scan every tenant, grouping by ``user_id``),
**idempotent**, and **resumable**:

* ``ArchivalSweepJob`` — archives eligible memories; already-archived memories
  drop out of the ACTIVE scan, so re-runs are no-ops.
* ``PromotionSweepJob`` — promotes promotable memories, guarded on
  ``not is_promoted`` so a re-run never double-bumps priority.
* ``DecaySweepJob`` — decay is inherently time-cumulative, so it carries a
  **period-stamp guard**: a memory already stamped for the current period is
  skipped, making a re-run idempotent and an interrupted run resumable.

A fresh ``MemoryIntelligenceService`` is created per operation (via a factory),
mirroring the consolidation pipeline, because the service holds a single Unit of
Work that is not reused across operations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.application.interfaces.scheduler import ScheduledJob
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus

IntelligenceFactory = Callable[[], MemoryIntelligenceService]
UowFactory = Callable[[], UnitOfWork]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SweepResult:
    name: str
    processed: int
    skipped: int
    tenants: int


class _BaseSweep(ScheduledJob):
    def __init__(
        self,
        uow_factory: UowFactory,
        intelligence_factory: IntelligenceFactory,
        *,
        now_fn: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._intelligence_factory = intelligence_factory
        self._now_fn = now_fn

    async def _active_by_tenant(self, user_id: UUID | None) -> dict[UUID, list[Memory]]:
        async with self._uow_factory() as uow:
            memories = await uow.memories.list_for_analytics(user_id)
        grouped: dict[UUID, list[Memory]] = {}
        for memory in memories:
            if memory.status is not MemoryStatus.ACTIVE:
                continue
            grouped.setdefault(memory.user_id, []).append(memory)
        return grouped


class DecaySweepJob(_BaseSweep):
    name = "decay_sweep"

    async def run(self) -> None:
        await self.run_sweep()

    async def run_sweep(self, *, user_id: UUID | None = None) -> SweepResult:
        now = self._now_fn()
        period = now.date().isoformat()
        processed = skipped = 0
        grouped = await self._active_by_tenant(user_id)
        for memories in grouped.values():
            for memory in memories:
                if memory.was_swept("decay_period", period):
                    skipped += 1
                    continue
                await self._intelligence_factory().decay_memory(memory.id, now=now)
                await self._stamp(memory.id, period)
                processed += 1
        return SweepResult(self.name, processed, skipped, len(grouped))

    async def _stamp(self, memory_id: UUID, period: str) -> None:
        async with self._uow_factory() as uow:
            memory = await uow.memories.get_by_id(memory_id)
            if memory is None:
                return
            memory.stamp_maintenance("decay_period", period)
            await uow.memories.update(memory)
            await uow.commit()


class ArchivalSweepJob(_BaseSweep):
    name = "archival_sweep"

    async def run(self) -> None:
        await self.run_sweep()

    async def run_sweep(self, *, user_id: UUID | None = None) -> SweepResult:
        now = self._now_fn()
        processed = skipped = 0
        grouped = await self._active_by_tenant(user_id)
        for memories in grouped.values():
            for memory in memories:
                evaluation = await self._intelligence_factory().evaluate_memory(memory.id, now=now)
                if evaluation.should_archive:
                    await self._intelligence_factory().archive_memory(
                        memory.id, force=True, now=now
                    )
                    processed += 1
                else:
                    skipped += 1
        return SweepResult(self.name, processed, skipped, len(grouped))


class PromotionSweepJob(_BaseSweep):
    name = "promotion_sweep"

    async def run(self) -> None:
        await self.run_sweep()

    async def run_sweep(self, *, user_id: UUID | None = None) -> SweepResult:
        now = self._now_fn()
        processed = skipped = 0
        grouped = await self._active_by_tenant(user_id)
        for memories in grouped.values():
            for memory in memories:
                if memory.is_promoted:  # idempotency: never double-promote
                    skipped += 1
                    continue
                evaluation = await self._intelligence_factory().evaluate_memory(memory.id, now=now)
                if evaluation.is_promotable:
                    await self._intelligence_factory().promote_memory(memory.id)
                    processed += 1
                else:
                    skipped += 1
        return SweepResult(self.name, processed, skipped, len(grouped))

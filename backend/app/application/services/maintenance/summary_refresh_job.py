"""SummaryRefreshJob — scheduled, tenant-aware summary refresh (Stage 11 Phase D).

Scans the corpus, finds every tenant with memories, and refreshes that tenant's
rolling summaries via ``MemorySummaryService``. Idempotent (the service upserts
and only versions on change) and resumable (each tenant refresh is independent).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.interfaces.scheduler import ScheduledJob
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.maintenance.memory_summary_service import MemorySummaryService


class SummaryRefreshJob(ScheduledJob):
    name = "summary_refresh"

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        summary_service: MemorySummaryService,
    ) -> None:
        self._uow_factory = uow_factory
        self._service = summary_service

    async def run(self) -> None:
        await self.run_sweep()

    async def run_sweep(self, *, user_id: UUID | None = None) -> int:
        async with self._uow_factory() as uow:
            memories = await uow.memories.list_for_analytics(user_id)
        tenants = {memory.user_id for memory in memories}
        for tenant in tenants:
            await self._service.refresh(tenant)
        return len(tenants)

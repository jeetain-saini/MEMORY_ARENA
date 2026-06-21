"""MemorySummaryService — generate & store rolling per-scope summaries.

For each configured scope (PROJECT / GOAL / EXPERIENCE) it gathers a tenant's
ACTIVE memories of that type, ranks them by score, asks the ``SummaryGenerator``
for a budget-bounded summary, and **upserts** one ``MemorySummary`` per
``(user, scope)``. Summaries are derived artifacts stored separately — the source
memories are never modified. Idempotent: an unchanged regeneration upserts the
same text without bumping the version.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.dto.auth_dto import AuthPrincipal
from app.application.dto.summary_dto import SummaryRefreshResult
from app.application.interfaces.summary_generator import SummaryGenerator
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.authorization import resolve_scope
from app.application.services.maintenance.config import MaintenanceConfig
from app.domain.entities.memory import Memory
from app.domain.entities.memory_summary import MemorySummary
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


class MemorySummaryService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        generator: SummaryGenerator,
        config: MaintenanceConfig | None = None,
        principal: AuthPrincipal | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._generator = generator
        self._config = config or MaintenanceConfig()
        self._principal = principal

    # -- reads (thin passthroughs to the repository) -----------------------
    async def list_for_user(self, user_id: UUID) -> list[MemorySummary]:
        user_id = resolve_scope(self._principal, user_id)
        async with self._uow_factory() as uow:
            return await uow.summaries.list_for_user(user_id)

    async def get(self, user_id: UUID, scope: MemoryType) -> MemorySummary | None:
        user_id = resolve_scope(self._principal, user_id)
        async with self._uow_factory() as uow:
            return await uow.summaries.get(user_id, scope)

    async def refresh(self, user_id: UUID) -> SummaryRefreshResult:
        async with self._uow_factory() as uow:
            memories = await uow.memories.list_for_analytics(user_id)

        created = updated = unchanged = 0
        for scope in self._config.summary_scopes:
            ranked = self._ranked(memories, scope)
            if not ranked:
                continue
            text = await self._generator.generate(
                scope, ranked, max_chars=self._config.summary_max_chars
            )
            source_ids = [m.id for m in ranked]
            outcome = await self._upsert(user_id, scope, text, source_ids)
            if outcome == "created":
                created += 1
            elif outcome == "updated":
                updated += 1
            else:
                unchanged += 1

        return SummaryRefreshResult(
            user_id=user_id,
            created=created,
            updated=updated,
            unchanged=unchanged,
            scopes=len(self._config.summary_scopes),
        )

    def _ranked(self, memories: list[Memory], scope: MemoryType) -> list[Memory]:
        scoped = [
            m for m in memories if m.memory_type is scope and m.status is MemoryStatus.ACTIVE
        ]
        scoped.sort(key=lambda m: m.total_score, reverse=True)
        return scoped[: self._config.summary_top_n]

    async def _upsert(
        self, user_id: UUID, scope: MemoryType, text: str, source_ids: list[UUID]
    ) -> str:
        async with self._uow_factory() as uow:
            existing = await uow.summaries.get(user_id, scope)
            if existing is None:
                summary = MemorySummary.create(
                    user_id=user_id, scope=scope, summary_text=text, source_memory_ids=source_ids
                )
                await uow.summaries.upsert(summary)
                await uow.commit()
                return "created"
            changed = existing.revise(summary_text=text, source_memory_ids=source_ids)
            await uow.summaries.upsert(existing)
            await uow.commit()
            return "updated" if changed else "unchanged"

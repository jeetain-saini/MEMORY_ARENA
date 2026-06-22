"""ForgettingEngine — configurable forgetting (Stage 17 Area 6).

A memory becomes FORGOTTEN (hidden from retrieval, never deleted) when it is
old AND low-importance AND rarely retrieved AND graph-isolated. All thresholds
are configurable; the rule is deterministic. Audit/version history is preserved.

Scheduler entry point: ``sweep_user(user_id, now=...)`` — idempotent (only ACTIVE
memories are considered; forgetting is recorded as a MemoryForgotten event).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.unit_of_work import UnitOfWork
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus

_logger = logging.getLogger("memoryarena.forgetting")


@dataclass(frozen=True)
class ForgettingConfig:
    min_age_days: int = 90            # only memories older than this
    max_importance: float = 0.25      # importance must be below this
    max_retrievals: int = 0           # retrieved at most this many times
    require_isolated: bool = True     # must have no graph edges
    protect_promoted: bool = True     # never forget a promoted memory


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


class ForgettingEngine:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        graph_repo: GraphRepository,
        dispatcher: EventDispatcher,
        config: ForgettingConfig | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._graph = graph_repo
        self._dispatcher = dispatcher
        self._config = config or ForgettingConfig()

    async def is_forgettable(
        self, memory: Memory, *, now: datetime, config: ForgettingConfig | None = None
    ) -> bool:
        c = config or self._config
        if memory.status is not MemoryStatus.ACTIVE:
            return False
        if c.protect_promoted and memory.is_promoted:
            return False
        age_days = (now - _aware(memory.updated_at)).days
        if age_days < c.min_age_days:
            return False
        if memory.score.importance > c.max_importance:
            return False
        if memory.retrieval_count > c.max_retrievals:
            return False
        if c.require_isolated:
            edges = await self._graph.get_edges(str(memory.id))
            if edges:
                return False
        return True

    async def sweep_user(
        self, user_id: UUID, *, now: datetime | None = None,
        config: ForgettingConfig | None = None,
    ) -> list[UUID]:
        """Forget all eligible memories for a user. Returns forgotten ids."""
        now = now or datetime.now(timezone.utc)
        async with self._uow_factory() as uow:
            memories = await uow.memories.list_for_analytics(user_id)

        forgotten: list[Memory] = []
        for m in memories:
            if await self.is_forgettable(m, now=now, config=config):
                m.forget(reason="aged_out: old, low-importance, rarely-retrieved, isolated")
                forgotten.append(m)

        if forgotten:
            async with self._uow_factory() as uow:
                for m in forgotten:
                    await uow.memories.update(m)
                await uow.commit()
            for m in forgotten:
                await self._dispatcher.dispatch(m.pull_events())
        _logger.info("forgetting.sweep", extra={"forgotten": len(forgotten)})
        return [m.id for m in forgotten]

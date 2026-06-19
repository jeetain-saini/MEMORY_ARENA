"""MemoryIntelligenceService — the Memory Intelligence Engine.

Evaluates and evolves memories over their lifetime: reinforce on reuse, decay
recency over time, promote high-value memories, and archive low-value, idle
ones. Pure evolution — no embeddings, retrieval, graph, or LLM calls.

Each operation runs in a Unit of Work, mutates the domain aggregate (which
enforces invariants and records events), persists, commits, then dispatches the
recorded domain events.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.application.dto.memory_dto import CreateMemoryResponse
from app.application.exceptions import MemoryNotFoundException, MemoryValidationException
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.presenters import memory_to_response
from app.application.services.decay_strategies import (
    DecayStrategy,
    ExponentialDecayStrategy,
)
from app.application.services.intelligence_config import IntelligenceConfig
from app.domain.entities.memory import Memory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryEvaluation:
    """Read-only assessment of a memory's current standing."""

    def __init__(self, *, total_score: float, is_promotable: bool, should_archive: bool) -> None:
        self.total_score = total_score
        self.is_promotable = is_promotable
        self.should_archive = should_archive


class MemoryIntelligenceService:
    def __init__(
        self,
        uow: UnitOfWork,
        dispatcher: EventDispatcher,
        config: IntelligenceConfig | None = None,
        decay_strategy: DecayStrategy | None = None,
    ) -> None:
        self._uow = uow
        self._dispatcher = dispatcher
        self._config = config or IntelligenceConfig()
        self._decay = decay_strategy or ExponentialDecayStrategy()

    # -- evaluation (calculate importance) ---------------------------------
    async def evaluate_memory(self, memory_id: UUID, *, now: datetime | None = None) -> MemoryEvaluation:
        async with self._uow as uow:
            memory = await uow.memories.get_by_id(memory_id)
        if memory is None:
            raise MemoryNotFoundException(memory_id)
        return self._evaluate(memory, now or _utcnow())

    # -- reinforcement -----------------------------------------------------
    async def reinforce_memory(
        self, memory_id: UUID, *, user_id: UUID | None = None, step: float | None = None
    ) -> CreateMemoryResponse:
        async with self._uow as uow:
            memory = await self._require(uow, memory_id, user_id)
            memory.reinforce(step if step is not None else self._config.reinforcement_step)
            updated = await uow.memories.update(memory)
            await uow.commit()
        await self._dispatcher.dispatch(memory.pull_events())
        return memory_to_response(updated)

    # -- decay -------------------------------------------------------------
    async def decay_memory(
        self, memory_id: UUID, *, now: datetime | None = None
    ) -> CreateMemoryResponse:
        async with self._uow as uow:
            memory = await self._require(uow, memory_id, None)
            factor = self._decay.compute_factor(memory, now or _utcnow())
            memory.decay(factor)
            updated = await uow.memories.update(memory)
            await uow.commit()
        await self._dispatcher.dispatch(memory.pull_events())
        return memory_to_response(updated)

    # -- promotion ---------------------------------------------------------
    async def promote_memory(
        self, memory_id: UUID, *, user_id: UUID | None = None
    ) -> CreateMemoryResponse:
        async with self._uow as uow:
            memory = await self._require(uow, memory_id, user_id)
            # Raises InvalidMemoryStateError (-> 409) if below the threshold.
            memory.promote(threshold=self._config.promotion_threshold)
            updated = await uow.memories.update(memory)
            await uow.commit()
        await self._dispatcher.dispatch(memory.pull_events())
        return memory_to_response(updated)

    # -- archival ----------------------------------------------------------
    async def archive_memory(
        self,
        memory_id: UUID,
        *,
        user_id: UUID | None = None,
        force: bool = False,
        now: datetime | None = None,
    ) -> CreateMemoryResponse:
        async with self._uow as uow:
            memory = await self._require(uow, memory_id, user_id)
            if not force and not self._should_archive(memory, now or _utcnow()):
                raise MemoryValidationException(
                    "Memory is not eligible for archival "
                    "(score above threshold or recently used)."
                )
            memory.archive()  # ACTIVE -> ARCHIVED; records MemoryArchived
            updated = await uow.memories.update(memory)
            await uow.commit()
        await self._dispatcher.dispatch(memory.pull_events())
        return memory_to_response(updated)

    # -- internals ---------------------------------------------------------
    async def _require(self, uow: UnitOfWork, memory_id: UUID, user_id: UUID | None) -> Memory:
        memory = await uow.memories.get_by_id(memory_id)
        if memory is None or (user_id is not None and memory.user_id != user_id):
            raise MemoryNotFoundException(memory_id)
        return memory

    def _evaluate(self, memory: Memory, now: datetime) -> MemoryEvaluation:
        return MemoryEvaluation(
            total_score=memory.total_score,
            is_promotable=memory.score.is_promotable(self._config.promotion_threshold),
            should_archive=self._should_archive(memory, now),
        )

    def _should_archive(self, memory: Memory, now: datetime) -> bool:
        reference = memory.updated_at
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        idle_days = (now - reference).total_seconds() / 86_400.0
        low_value = memory.total_score < self._config.archival_score_threshold
        long_idle = idle_days >= self._config.archival_max_idle_days
        return low_value and long_idle

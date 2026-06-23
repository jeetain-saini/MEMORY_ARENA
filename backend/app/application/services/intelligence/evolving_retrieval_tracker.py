"""EvolvingRetrievalTracker — retrieval frequency + reactive importance (Stage 17.1).

Stage 17 captured retrieval frequency but did nothing with it. This tracker
closes the loop: when retrieval returns a memory, it bumps the memory's
``retrieval_count``/``last_retrieved_at`` *and* re-evolves its importance via the
``ImportanceEvolutionService`` from the fresh count (plus the memory's existing
recency / promotion signals), persisting the new ``MemoryScore``.

It implements the same ``RetrievalTracker`` port the retrieval service already
depends on, so wiring is a one-line swap in the composition root and the
retrieval pipeline is unchanged. Graph centrality is left at its neutral default
on this hot path (a per-search graph lookup would be too costly); the periodic
``MemoryIntelligenceMaintenanceJob`` supplies the full graph-aware recompute.

Failure-isolated: a tracking/evolution error is logged and swallowed so it can
never break a search (identical guarantee to the original tracker).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from app.application.interfaces.retrieval_tracker import RetrievalTracker
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.intelligence.importance_evolution import (
    ImportanceEvolutionService,
)

_logger = logging.getLogger("memoryarena.retrieval")


class EvolvingRetrievalTracker(RetrievalTracker):
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        evolution: ImportanceEvolutionService | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._evolution = evolution or ImportanceEvolutionService()

    async def record(self, memory_ids: list[UUID]) -> None:
        if not memory_ids:
            return
        try:
            async with self._uow_factory() as uow:
                for memory_id in memory_ids:
                    memory = await uow.memories.get_by_id(memory_id)
                    if memory is None:
                        continue
                    # 1) record the retrieval (count + timestamp; not an "edit").
                    memory.record_retrieval()
                    # 2) evolve importance from the fresh count and persist.
                    memory.score = self._evolution.evolve(memory)
                    await uow.memories.update(memory)
                await uow.commit()
        except Exception:  # noqa: BLE001 — retrieval must never fail on tracking
            _logger.warning("retrieval.tracking_failed", exc_info=True)

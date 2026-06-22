"""UnitOfWork-backed RetrievalTracker (Stage 17 Area 3).

Bulk-increments retrieval_count + last_retrieved_at for the returned memories in
a short, independent transaction. Failure-isolated so a tracking hiccup never
breaks retrieval.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from app.application.interfaces.retrieval_tracker import RetrievalTracker
from app.application.interfaces.unit_of_work import UnitOfWork

_logger = logging.getLogger("memoryarena.retrieval")


class UnitOfWorkRetrievalTracker(RetrievalTracker):
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def record(self, memory_ids: list[UUID]) -> None:
        if not memory_ids:
            return
        try:
            async with self._uow_factory() as uow:
                await uow.memories.record_retrievals(memory_ids)
                await uow.commit()
        except Exception:  # noqa: BLE001 — retrieval must never fail on tracking
            _logger.warning("retrieval.tracking_failed", exc_info=True)

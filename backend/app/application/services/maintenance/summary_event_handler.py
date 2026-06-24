"""SummaryRefreshEventHandler — keep rolling summaries fresh on every change.

Refreshes a user's summaries the moment their memory set changes, so summaries
no longer depend on the scheduled maintenance sweep:

  MemoryCreated / MemoryArchived / MemorySuperseded -> refresh(user_id)

The deterministic generator is cheap (no LLM), and refresh is idempotent (it
only versions a summary when the text actually changes). Filtering to ACTIVE
memories means an archived/superseded memory drops out of the summary, so the
summary always reflects the latest truth (e.g. after a contradiction supersedes
the old favourite). Failure-isolated — a refresh error never breaks the write
that triggered it.
"""

from __future__ import annotations

import logging

from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.services.maintenance.memory_summary_service import MemorySummaryService
from app.domain.events.memory_events import (
    MemoryArchived,
    MemoryCreated,
    MemorySuperseded,
)

_logger = logging.getLogger("memoryarena.summary")


class SummaryRefreshEventHandler:
    def __init__(self, summary_service: MemorySummaryService) -> None:
        self._service = summary_service

    async def _refresh(self, user_id) -> None:  # noqa: ANN001
        try:
            await self._service.refresh(user_id)
        except Exception:  # noqa: BLE001 — summary refresh must never break a write
            _logger.warning("summary.refresh_failed", exc_info=True, extra={"user_id": str(user_id)})

    async def on_memory_created(self, event: MemoryCreated) -> None:
        await self._refresh(event.user_id)

    async def on_memory_archived(self, event: MemoryArchived) -> None:
        await self._refresh(event.user_id)

    async def on_memory_superseded(self, event: MemorySuperseded) -> None:
        await self._refresh(event.user_id)

    def register(self, dispatcher: EventDispatcher) -> None:
        dispatcher.register(MemoryCreated, self.on_memory_created)
        dispatcher.register(MemoryArchived, self.on_memory_archived)
        dispatcher.register(MemorySuperseded, self.on_memory_superseded)

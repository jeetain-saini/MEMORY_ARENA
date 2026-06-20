"""ConsolidationEventHandler — bridges domain events to the consolidation pipeline.

Subscribes to MemoryCreated only (never MemoryArchived — avoids circular chains).
Mirrors GraphEventHandler and EmbeddingEventHandler in structure.
"""

from __future__ import annotations

from app.application.interfaces.consolidation_job_processor import (
    ConsolidationJob,
    ConsolidationJobProcessor,
)
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.domain.events.memory_events import MemoryCreated


class ConsolidationEventHandler:
    def __init__(self, processor: ConsolidationJobProcessor) -> None:
        self._processor = processor

    async def on_memory_created(self, event: MemoryCreated) -> None:
        await self._processor.submit(
            ConsolidationJob(memory_id=event.memory_id, user_id=event.user_id)
        )

    def register(self, dispatcher: EventDispatcher) -> None:
        dispatcher.register(MemoryCreated, self.on_memory_created)

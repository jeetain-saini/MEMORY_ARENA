"""InferenceEventHandler — bridge MemoryCreated to relationship inference.

  MemoryCreated -> submit an InferenceJob

Event-driven only: the use case records the event; this handler submits a job to
the (async, swappable) maintenance processor, so inference runs off the request's
critical path — mirroring the embedding / graph / consolidation handlers. It
subscribes to ``MemoryCreated`` only, so no inference action can trigger another
inference cycle.
"""

from __future__ import annotations

from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.maintenance_job_processor import (
    InferenceJob,
    MaintenanceJobProcessor,
)
from app.domain.events.memory_events import MemoryCreated


class InferenceEventHandler:
    def __init__(self, processor: MaintenanceJobProcessor) -> None:
        self._processor = processor

    async def on_memory_created(self, event: MemoryCreated) -> None:
        await self._processor.submit(
            InferenceJob(memory_id=event.memory_id, user_id=event.user_id)
        )

    def register(self, dispatcher: EventDispatcher) -> None:
        dispatcher.register(MemoryCreated, self.on_memory_created)

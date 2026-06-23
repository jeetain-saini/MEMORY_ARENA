"""IntelligenceEventHandler — bridge MemoryCreated to autonomous evolution.

  MemoryCreated -> submit an IntelligenceJob (promotion + clustering re-eval)

Event-driven only: the use case records ``MemoryCreated``; this handler submits a
job to the (async, swappable) intelligence processor so promotion/clustering run
off the request's critical path — mirroring the embedding / graph / inference
handlers. It subscribes to ``MemoryCreated`` only, so the semantic memories the
promotion engine itself creates do not trigger an unbounded re-evaluation loop
beyond their own (idempotent) pass.
"""

from __future__ import annotations

from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.intelligence_job_processor import (
    IntelligenceJob,
    IntelligenceJobProcessor,
)
from app.domain.events.memory_events import MemoryCreated


class IntelligenceEventHandler:
    def __init__(self, processor: IntelligenceJobProcessor) -> None:
        self._processor = processor

    async def on_memory_created(self, event: MemoryCreated) -> None:
        await self._processor.submit(IntelligenceJob(user_id=event.user_id))

    def register(self, dispatcher: EventDispatcher) -> None:
        dispatcher.register(MemoryCreated, self.on_memory_created)

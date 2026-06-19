"""EmbeddingEventHandler — bridges memory domain events to embedding jobs.

Subscribes to the memory lifecycle events and translates them into embedding
jobs submitted to the (async, swappable) job processor. This keeps embedding
generation fully event-driven: producers (use cases) never call the embedding
pipeline directly — they only record domain events.

  MemoryCreated / MemoryUpdated -> UPSERT   (generate + store)
  MemoryDeleted                 -> DELETE   (remove embeddings)
"""

from __future__ import annotations

from app.application.interfaces.embedding_job_processor import (
    EmbeddingAction,
    EmbeddingJob,
    EmbeddingJobProcessor,
)
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.domain.events.memory_events import (
    MemoryCreated,
    MemoryDeleted,
    MemoryUpdated,
)


class EmbeddingEventHandler:
    def __init__(self, processor: EmbeddingJobProcessor) -> None:
        self._processor = processor

    async def on_memory_created(self, event: MemoryCreated) -> None:
        await self._processor.submit(EmbeddingJob(EmbeddingAction.UPSERT, event.memory_id))

    async def on_memory_updated(self, event: MemoryUpdated) -> None:
        await self._processor.submit(EmbeddingJob(EmbeddingAction.UPSERT, event.memory_id))

    async def on_memory_deleted(self, event: MemoryDeleted) -> None:
        await self._processor.submit(EmbeddingJob(EmbeddingAction.DELETE, event.memory_id))

    def register(self, dispatcher: EventDispatcher) -> None:
        dispatcher.register(MemoryCreated, self.on_memory_created)
        dispatcher.register(MemoryUpdated, self.on_memory_updated)
        dispatcher.register(MemoryDeleted, self.on_memory_deleted)

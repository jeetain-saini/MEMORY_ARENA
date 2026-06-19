"""GraphEventHandler — bridges memory domain events to graph-sync jobs.

  MemoryCreated / MemoryUpdated -> SYNC   (upsert node + re-derive edges)
  MemoryDeleted                 -> REMOVE (remove node)

Event-driven only: use cases record events; this handler submits jobs to the
(async, swappable) graph job processor, so graph sync runs off the request's
critical path — mirroring the Stage 6 embedding pipeline.
"""

from __future__ import annotations

from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.graph_job_processor import (
    GraphJobProcessor,
    GraphSyncAction,
    GraphSyncJob,
)
from app.domain.events.memory_events import (
    MemoryCreated,
    MemoryDeleted,
    MemoryUpdated,
)


class GraphEventHandler:
    def __init__(self, processor: GraphJobProcessor) -> None:
        self._processor = processor

    async def on_memory_created(self, event: MemoryCreated) -> None:
        await self._processor.submit(GraphSyncJob(GraphSyncAction.SYNC, event.memory_id))

    async def on_memory_updated(self, event: MemoryUpdated) -> None:
        await self._processor.submit(GraphSyncJob(GraphSyncAction.SYNC, event.memory_id))

    async def on_memory_deleted(self, event: MemoryDeleted) -> None:
        await self._processor.submit(GraphSyncJob(GraphSyncAction.REMOVE, event.memory_id))

    def register(self, dispatcher: EventDispatcher) -> None:
        dispatcher.register(MemoryCreated, self.on_memory_created)
        dispatcher.register(MemoryUpdated, self.on_memory_updated)
        dispatcher.register(MemoryDeleted, self.on_memory_deleted)

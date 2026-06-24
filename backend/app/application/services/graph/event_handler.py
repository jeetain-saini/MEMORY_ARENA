"""GraphEventHandler — bridges memory domain events to graph-sync jobs.

  MemoryCreated / MemoryUpdated                       -> SYNC   (upsert node + edges)
  MemoryArchived / MemorySuperseded / MemoryForgotten -> SYNC   (refresh node status)
  MemoryDeleted                                       -> REMOVE (remove node)

A status change (archive/supersede/forget) re-syncs the node so its ``status``
property reflects the new state. This matters for retrieval: graph expansion
filters neighbours by status, so without the refresh an archived/superseded
memory (e.g. the old favourite after a contradiction) would keep resurfacing as
an ACTIVE neighbour.

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
    MemoryArchived,
    MemoryCreated,
    MemoryDeleted,
    MemoryForgotten,
    MemorySuperseded,
    MemoryUpdated,
)


class GraphEventHandler:
    def __init__(self, processor: GraphJobProcessor) -> None:
        self._processor = processor

    async def _sync(self, memory_id) -> None:  # noqa: ANN001
        await self._processor.submit(GraphSyncJob(GraphSyncAction.SYNC, memory_id))

    async def on_memory_created(self, event: MemoryCreated) -> None:
        await self._sync(event.memory_id)

    async def on_memory_updated(self, event: MemoryUpdated) -> None:
        await self._sync(event.memory_id)

    async def on_memory_archived(self, event: MemoryArchived) -> None:
        await self._sync(event.memory_id)

    async def on_memory_superseded(self, event: MemorySuperseded) -> None:
        await self._sync(event.memory_id)

    async def on_memory_forgotten(self, event: MemoryForgotten) -> None:
        await self._sync(event.memory_id)

    async def on_memory_deleted(self, event: MemoryDeleted) -> None:
        await self._processor.submit(GraphSyncJob(GraphSyncAction.REMOVE, event.memory_id))

    def register(self, dispatcher: EventDispatcher) -> None:
        dispatcher.register(MemoryCreated, self.on_memory_created)
        dispatcher.register(MemoryUpdated, self.on_memory_updated)
        dispatcher.register(MemoryArchived, self.on_memory_archived)
        dispatcher.register(MemorySuperseded, self.on_memory_superseded)
        dispatcher.register(MemoryForgotten, self.on_memory_forgotten)
        dispatcher.register(MemoryDeleted, self.on_memory_deleted)

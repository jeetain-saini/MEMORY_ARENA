"""CacheInvalidationEventHandler — clears stale read aggregates on a write.

Subscribes to every memory-mutation domain event and deletes the writer's cached
analytics/health keys **and** the global keys (broad, correctness-first). Runs
post-commit via the in-process dispatcher (failure-isolated like the other
handlers), so a cache hiccup can never break a write; the cache TTL is the
secondary safety net.
"""

from __future__ import annotations

from app.application.interfaces.cache_provider import CacheProvider
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.services.cache.cache_keys import invalidation_keys
from app.domain.events.memory_events import (
    DomainEvent,
    MemoryArchived,
    MemoryCreated,
    MemoryDecayed,
    MemoryDeleted,
    MemoryPromoted,
    MemoryReinforced,
    MemoryUpdated,
)

# Every mutation that can change an analytics/health aggregate.
_MUTATION_EVENTS = (
    MemoryCreated,
    MemoryUpdated,
    MemoryArchived,
    MemoryDeleted,
    MemoryPromoted,
    MemoryReinforced,
    MemoryDecayed,
)


class CacheInvalidationEventHandler:
    def __init__(self, cache: CacheProvider) -> None:
        self._cache = cache

    async def on_memory_mutation(self, event: DomainEvent) -> None:
        user_id = getattr(event, "user_id", None)
        if user_id is None:
            return
        for key in invalidation_keys(user_id):
            await self._cache.delete(key)

    def register(self, dispatcher: EventDispatcher) -> None:
        for event_type in _MUTATION_EVENTS:
            dispatcher.register(event_type, self.on_memory_mutation)

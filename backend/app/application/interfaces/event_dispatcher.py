"""EventDispatcher port — the boundary for publishing domain events.

Use cases record domain events on the aggregate and, after the transaction
commits, hand them to a dispatcher. The application depends only on this
abstraction; whether events are handled in-process (Stage 4) or shipped to
Kafka/RabbitMQ (future) is an infrastructure choice swapped behind this port.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterable

from app.domain.events.memory_events import DomainEvent

# A handler may be sync or async; the dispatcher awaits awaitable results.
EventHandler = Callable[[DomainEvent], Awaitable[None] | None]


class EventDispatcher(ABC):
    """Publishes domain events to registered handlers."""

    @abstractmethod
    def register(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Subscribe ``handler`` to ``event_type`` (and its subclasses)."""

    @abstractmethod
    async def dispatch(self, events: Iterable[DomainEvent]) -> None:
        """Publish each event to all matching handlers."""

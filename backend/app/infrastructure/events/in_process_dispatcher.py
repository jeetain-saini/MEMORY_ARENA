"""InProcessEventDispatcher — synchronous, in-memory event delivery.

A minimal dispatcher that invokes registered handlers in the same process.
Handlers are matched along the event's MRO, so registering for the base
``DomainEvent`` yields a catch-all (handy for a future Kafka/RabbitMQ forwarder:
one handler can publish every event to a broker without code changes here).

Handler failures are isolated and logged — one bad subscriber must never break
the request or starve the others. Swapping this for a real message bus later is
a drop-in replacement behind the ``EventDispatcher`` port.
"""

from __future__ import annotations

import inspect
import logging
from collections import defaultdict
from collections.abc import Iterable

from app.application.interfaces.event_dispatcher import EventDispatcher, EventHandler
from app.domain.events.memory_events import DomainEvent

_logger = logging.getLogger("memoryarena.events")


class InProcessEventDispatcher(EventDispatcher):
    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def register(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def dispatch(self, events: Iterable[DomainEvent]) -> None:
        for event in events:
            for event_type in type(event).__mro__:
                for handler in self._handlers.get(event_type, []):
                    await self._invoke(handler, event)

    @staticmethod
    async def _invoke(handler: EventHandler, event: DomainEvent) -> None:
        try:
            result = handler(event)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 - isolate handler failures
            _logger.exception("event.handler.failed", extra={"event": type(event).__name__})


def _log_event(event: DomainEvent) -> None:
    _logger.info("domain.event", extra={"event": type(event).__name__, "event_id": str(event.event_id)})


# Process-wide singleton with a default audit-logging handler for all events.
in_process_dispatcher = InProcessEventDispatcher()
in_process_dispatcher.register(DomainEvent, _log_event)

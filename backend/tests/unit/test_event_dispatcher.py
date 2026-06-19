"""Tests for the in-process domain event dispatcher."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.domain.events.memory_events import DomainEvent, MemoryCreated, MemoryUpdated
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher


def _created() -> MemoryCreated:
    return MemoryCreated(memory_id=uuid4(), user_id=uuid4(), memory_type=MemoryType.FACT)


def _updated() -> MemoryUpdated:
    return MemoryUpdated(memory_id=uuid4(), user_id=uuid4(), version=2)


def test_handler_receives_matching_event() -> None:
    dispatcher = InProcessEventDispatcher()
    received: list[DomainEvent] = []
    dispatcher.register(MemoryCreated, received.append)

    event = _created()
    asyncio.run(dispatcher.dispatch([event]))
    assert received == [event]


def test_base_registration_is_catch_all() -> None:
    dispatcher = InProcessEventDispatcher()
    seen: list[str] = []
    dispatcher.register(DomainEvent, lambda e: seen.append(type(e).__name__))

    asyncio.run(dispatcher.dispatch([_created(), _updated()]))
    assert seen == ["MemoryCreated", "MemoryUpdated"]


def test_async_handler_is_awaited() -> None:
    dispatcher = InProcessEventDispatcher()
    flag: dict[str, bool] = {}

    async def handler(_: DomainEvent) -> None:
        flag["called"] = True

    dispatcher.register(MemoryCreated, handler)
    asyncio.run(dispatcher.dispatch([_created()]))
    assert flag.get("called") is True


def test_handler_failure_is_isolated() -> None:
    dispatcher = InProcessEventDispatcher()
    survivors: list[int] = []

    def bad(_: DomainEvent) -> None:
        raise RuntimeError("boom")

    dispatcher.register(MemoryCreated, bad)
    dispatcher.register(MemoryCreated, lambda _: survivors.append(1))

    # Must not raise despite the failing handler.
    asyncio.run(dispatcher.dispatch([_created()]))
    assert survivors == [1]

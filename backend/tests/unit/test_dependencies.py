"""Dependency-injection wiring tests."""

from __future__ import annotations

from app.api.v1.dependencies.providers import (
    get_event_dispatcher,
    get_memory_service,
)
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.services.memory_service import MemoryService
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher


def test_event_dispatcher_is_singleton() -> None:
    a = get_event_dispatcher()
    b = get_event_dispatcher()
    assert a is b
    assert isinstance(a, EventDispatcher)
    assert isinstance(a, InProcessEventDispatcher)


def test_get_memory_service_assembles_service() -> None:
    # Provide the collaborators directly (the FastAPI Depends defaults are only
    # resolved inside a request); this verifies the wiring shape.
    class _FakeUoW:  # minimal stand-in; service construction must not touch it
        pass

    service = get_memory_service(uow=_FakeUoW(), dispatcher=get_event_dispatcher())
    assert isinstance(service, MemoryService)
    for method in ("create", "update", "delete", "search", "get_by_id", "list_by_user"):
        assert hasattr(service, method)

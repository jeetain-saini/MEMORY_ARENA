"""Stage 19.3 — audit logging tests.

Proves the catch-all audit handler records every memory write, lifecycle
transition, and intelligence action that flows through the event dispatcher, and
that entries carry actor/resource/metadata. In-memory dispatcher + audit sink
(no DB); the Postgres adapter shares the AuditLog contract.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.dto.audit_dto import AuditEntry
from app.application.services.audit.audit_event_handler import AuditEventHandler
from app.domain.events.memory_events import (
    MemoryCreated,
    MemoryForgotten,
    MemoryPromoted,
    MemorySuperseded,
    MemoryUpdated,
)
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.audit.in_memory_audit_log import InMemoryAuditLog
from app.infrastructure.audit.postgres_audit_log import PostgresAuditLog
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from tests.integration._db import make_engine

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def test_audit_records_every_event_type() -> None:
    async def scenario() -> None:
        user = uuid4()
        m1, m2 = uuid4(), uuid4()
        audit = InMemoryAuditLog()
        dispatcher = InProcessEventDispatcher()
        AuditEventHandler(audit).register(dispatcher)

        await dispatcher.dispatch([
            MemoryCreated(memory_id=m1, user_id=user, memory_type=MemoryType.FACT),
            MemoryUpdated(memory_id=m1, user_id=user, version=2, reason="edit"),
            MemoryPromoted(memory_id=m1, user_id=user, total_score=0.9, priority=3),
            MemoryForgotten(memory_id=m2, user_id=user, reason="aged_out"),
            MemorySuperseded(memory_id=m2, superseded_by_id=m1, user_id=user),
        ])

        entries = await audit.list_for_user(user, limit=50)
        assert len(entries) == 5
        actions = {e.action for e in entries}
        assert actions == {
            "MemoryCreated", "MemoryUpdated", "MemoryPromoted",
            "MemoryForgotten", "MemorySuperseded",
        }
        # Every entry is attributed to the tenant and the affected resource.
        assert all(e.user_id == user for e in entries)
        assert all(e.resource_type == "memory" for e in entries)
        assert all(e.resource_id is not None for e in entries)

    _run(scenario)


def test_audit_captures_event_metadata() -> None:
    async def scenario() -> None:
        user = uuid4()
        mem = uuid4()
        audit = InMemoryAuditLog()
        dispatcher = InProcessEventDispatcher()
        AuditEventHandler(audit).register(dispatcher)

        await dispatcher.dispatch([
            MemoryUpdated(memory_id=mem, user_id=user, version=7, reason="content_change"),
        ])
        [entry] = await audit.list_for_user(user)
        assert entry.action == "MemoryUpdated"
        assert entry.resource_id == mem
        assert entry.metadata["version"] == 7
        assert entry.metadata["reason"] == "content_change"
        # user_id/resource ids are not duplicated into metadata.
        assert "user_id" not in entry.metadata
        assert "memory_id" not in entry.metadata

    _run(scenario)


def test_audit_newest_first_and_isolated_per_tenant() -> None:
    async def scenario() -> None:
        a, b = uuid4(), uuid4()
        audit = InMemoryAuditLog()
        dispatcher = InProcessEventDispatcher()
        AuditEventHandler(audit).register(dispatcher)

        await dispatcher.dispatch([
            MemoryCreated(memory_id=uuid4(), user_id=a, memory_type=MemoryType.FACT),
            MemoryCreated(memory_id=uuid4(), user_id=b, memory_type=MemoryType.FACT),
            MemoryForgotten(memory_id=uuid4(), user_id=a, reason="x"),
        ])
        a_entries = await audit.list_for_user(a)
        b_entries = await audit.list_for_user(b)
        # tenant isolation: each only sees its own actions.
        assert len(a_entries) == 2
        assert len(b_entries) == 1
        # newest first.
        assert a_entries[0].action == "MemoryForgotten"

    _run(scenario)


def test_audit_record_failure_never_raises() -> None:
    async def scenario() -> None:
        class BrokenAudit(InMemoryAuditLog):
            async def record(self, entry):  # type: ignore[override]
                raise RuntimeError("sink down")

        dispatcher = InProcessEventDispatcher()
        AuditEventHandler(BrokenAudit()).register(dispatcher)
        # Dispatcher isolates handler failures -> dispatch still completes.
        await dispatcher.dispatch([
            MemoryCreated(memory_id=uuid4(), user_id=uuid4(), memory_type=MemoryType.FACT),
        ])

    _run(scenario)


# --- durable Postgres adapter (SQLite-backed in tests) ---------------------

def test_postgres_audit_log_round_trips_and_orders_newest_first() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        sf = create_session_factory(engine)
        audit = PostgresAuditLog(sf)
        user = uuid4()
        m = uuid4()

        await audit.record(AuditEntry(
            action="MemoryCreated", resource_type="memory",
            user_id=user, resource_id=m, actor_role="user",
            metadata={"memory_type": "fact"},
        ))
        await audit.record(AuditEntry(
            action="intelligence.promote", resource_type="intelligence",
            user_id=user, resource_id=m, actor_role="admin",
            metadata={"sources": 3},
        ))

        entries = await audit.list_for_user(user, limit=10)
        assert len(entries) == 2
        assert entries[0].action == "intelligence.promote"   # newest first
        assert entries[0].actor_role == "admin"
        assert entries[0].metadata == {"sources": 3}
        assert entries[1].action == "MemoryCreated"
        assert entries[1].resource_id == m
        # tenant isolation: a different user sees nothing.
        assert await audit.list_for_user(uuid4()) == []
        await engine.dispose()

    _run(scenario)


def test_audit_handler_persists_through_postgres_adapter() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        sf = create_session_factory(engine)
        audit = PostgresAuditLog(sf)
        dispatcher = InProcessEventDispatcher()
        AuditEventHandler(audit).register(dispatcher)
        user = uuid4()

        await dispatcher.dispatch([
            MemoryCreated(memory_id=uuid4(), user_id=user, memory_type=MemoryType.FACT),
            MemoryForgotten(memory_id=uuid4(), user_id=user, reason="aged_out"),
        ])
        entries = await audit.list_for_user(user)
        assert {e.action for e in entries} == {"MemoryCreated", "MemoryForgotten"}
        await engine.dispose()

    _run(scenario)

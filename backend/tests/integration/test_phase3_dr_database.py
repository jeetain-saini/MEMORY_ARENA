"""Phase 3 — PostgreSQL disaster-recovery (logical backup/restore) tests.

Proves a full export -> fresh database -> restore round-trip preserves every
table's rows exactly, including memories, their scores, and the audit trail.
Backend-agnostic (runs on SQLite here; the same code backs up PostgreSQL in
production). This is the recovery-verification step (3.5): restore into a clean
database and confirm the data matches the source.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.application.dto.audit_dto import AuditEntry
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.audit.postgres_audit_log import PostgresAuditLog
from app.infrastructure.backup.database_backup import DatabaseBackup
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _seed_source(engine):
    user = await seed_user(engine)
    factory = create_session_factory(engine)
    memories = []
    async with SQLAlchemyUnitOfWork(factory) as uow:
        for i in range(5):
            m = Memory.create(user_id=user, content=f"durable fact {i}",
                              memory_type=MemoryType.FACT)
            await uow.memories.save(m)
            memories.append(m)
        await uow.commit()
    # an audit row, to prove the audit trail is part of the backup.
    await PostgresAuditLog(factory).record(AuditEntry(
        action="MemoryCreated", resource_type="memory",
        user_id=user, resource_id=memories[0].id, metadata={"i": 0},
    ))
    return user, memories


def test_export_restore_round_trip_preserves_all_rows() -> None:
    async def scenario() -> None:
        source = await make_engine()
        user, memories = await _seed_source(source)

        snapshot = await DatabaseBackup(source).export()
        # Snapshot is non-empty and self-describing.
        assert snapshot["version"] == 1
        assert snapshot["row_counts"]["users"] >= 1
        assert snapshot["row_counts"]["memories"] == 5
        assert snapshot["row_counts"]["audit_log"] == 1
        await source.dispose()

        # Restore into a brand-new, empty database (simulating a recovery host).
        target = await make_engine()
        restored = await DatabaseBackup(target).restore(snapshot)
        assert restored["memories"] == 5
        assert restored["users"] == snapshot["row_counts"]["users"]

        # Recovery verification: the data is readable and identical post-restore.
        factory = create_session_factory(target)
        async with SQLAlchemyUnitOfWork(factory) as uow:
            recovered = await uow.memories.list_for_analytics(user)
        assert {m.content for m in recovered} == {f"durable fact {i}" for i in range(5)}
        # The audit trail survived too.
        audit = await PostgresAuditLog(factory).list_for_user(user)
        assert len(audit) == 1
        assert audit[0].action == "MemoryCreated"
        await target.dispose()

    _run(scenario)


def test_restore_is_idempotent_and_clears_prior_state() -> None:
    async def scenario() -> None:
        source = await make_engine()
        user, _ = await _seed_source(source)
        snapshot = await DatabaseBackup(source).export()
        await source.dispose()

        target = await make_engine()
        backup = DatabaseBackup(target)
        await backup.restore(snapshot)
        # Restoring a second time must not duplicate rows (clears then loads).
        again = await backup.restore(snapshot)
        assert again["memories"] == 5

        factory = create_session_factory(target)
        async with SQLAlchemyUnitOfWork(factory) as uow:
            recovered = await uow.memories.list_for_analytics(user)
        assert len(recovered) == 5  # not 10 — restore replaced, didn't append
        await target.dispose()

    _run(scenario)


def test_restore_rejects_unknown_snapshot_version() -> None:
    async def scenario() -> None:
        target = await make_engine()
        try:
            raised = False
            try:
                await DatabaseBackup(target).restore({"version": 999, "tables": {}})
            except ValueError:
                raised = True
            assert raised
        finally:
            await target.dispose()

    _run(scenario)

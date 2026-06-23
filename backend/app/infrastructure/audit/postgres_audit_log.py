"""PostgresAuditLog — durable, queryable audit trail (production adapter).

Selected when ``AUDIT_BACKEND=postgres``. Each entry is inserted in its own short
transaction (the audit handler runs *after* the request's unit of work commits,
so it owns its own session). Writes are best-effort: a failure to audit is logged
and swallowed so it never breaks the audited operation — the trail may miss a row
under a database outage, but the user's action still succeeds.

Behavioral parity with the in-memory adapter is guaranteed by the shared
``AuditLog`` contract; exercised against a real PostgreSQL/SQLite session.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.audit_dto import AuditEntry
from app.application.interfaces.audit_log import AuditLog
from app.infrastructure.database.models.audit_log import AuditLogModel

_logger = logging.getLogger("memoryarena.audit")


class PostgresAuditLog(AuditLog):
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, entry: AuditEntry) -> None:
        try:
            async with self._session_factory() as session:
                session.add(
                    AuditLogModel(
                        id=entry.entry_id,
                        action=entry.action,
                        resource_type=entry.resource_type,
                        user_id=entry.user_id,
                        resource_id=entry.resource_id,
                        actor_role=entry.actor_role,
                        details=dict(entry.metadata),
                        occurred_at=entry.occurred_at,
                    )
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001 — auditing must never break the action
            _logger.warning("audit.record_failed", extra={"action": entry.action, "error": str(exc)})

    async def list_for_user(self, user_id: UUID, *, limit: int = 100) -> list[AuditEntry]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(AuditLogModel)
                    .where(AuditLogModel.user_id == user_id)
                    .order_by(AuditLogModel.occurred_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        return [
            AuditEntry(
                action=r.action,
                resource_type=r.resource_type,
                user_id=r.user_id,
                resource_id=r.resource_id,
                actor_role=r.actor_role,
                metadata=dict(r.details or {}),
                occurred_at=r.occurred_at,
                entry_id=r.id,
            )
            for r in rows
        ]

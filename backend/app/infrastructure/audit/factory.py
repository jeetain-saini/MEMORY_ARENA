"""Audit-log factory — config-driven selection (Stage 19.3).

``InMemoryAuditLog`` by default (offline/dev/tests, no DB writes on the audit
path); the durable ``PostgresAuditLog`` when ``AUDIT_BACKEND=postgres``. Mirrors
the other infrastructure factories. The Postgres session factory is supplied by
the composition root so this stays free of connection wiring.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.audit_log import AuditLog
from app.core.config import get_settings
from app.infrastructure.audit.in_memory_audit_log import InMemoryAuditLog


def build_audit_log(
    session_factory: Callable[[], AsyncSession] | None = None,
) -> AuditLog:
    settings = get_settings()
    if settings.audit_backend == "postgres" and session_factory is not None:
        from app.infrastructure.audit.postgres_audit_log import PostgresAuditLog

        return PostgresAuditLog(session_factory)
    return InMemoryAuditLog()

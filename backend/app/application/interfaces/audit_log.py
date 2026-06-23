"""AuditLog port — append-only record of security-relevant actions (Stage 19.3).

Every write, memory-lifecycle transition, and intelligence action is recorded
through this port so there is a durable, queryable trail of who did what to which
resource. The application depends only on this abstraction; a Postgres-backed
adapter persists in production, an in-memory adapter serves the offline suite,
and a structured-log adapter is available where a log pipeline is the system of
record. Writes are best-effort from the caller's perspective — auditing must
never break the audited operation — so adapters swallow/log their own failures.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.audit_dto import AuditEntry


class AuditLog(ABC):
    @abstractmethod
    async def record(self, entry: AuditEntry) -> None:
        """Append one audit entry (best-effort; never raises to the caller)."""

    @abstractmethod
    async def list_for_user(self, user_id: UUID, *, limit: int = 100) -> list[AuditEntry]:
        """Return a tenant's recent audit entries, newest first (for admin/verification)."""

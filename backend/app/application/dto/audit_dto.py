"""Audit DTOs (Stage 19.3).

A framework-free record of a security-relevant action: who (``user_id`` /
``actor_role``), what (``action``), on which resource (``resource_type`` /
``resource_id``), when (``occurred_at``), and any structured detail
(``metadata``). Adapters persist these; the application never sees storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AuditEntry:
    action: str                       # e.g. "MemoryCreated", "intelligence.promote"
    resource_type: str                # e.g. "memory", "intelligence", "auth"
    user_id: UUID | None = None       # the tenant the action belongs to
    resource_id: UUID | None = None   # the affected resource, when applicable
    actor_role: str | None = None     # RBAC role of the caller, when known
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=_utcnow)
    entry_id: UUID = field(default_factory=uuid4)

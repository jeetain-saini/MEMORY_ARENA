"""Domain events for the memory aggregate.

Events are immutable facts about something that has already happened ("Memory
was archived"). Entities record them as side effects of behavior; the
application layer later pulls and dispatches them (e.g. to update the graph,
trigger consolidation, or emit analytics) — all without the domain knowing who
listens. This is the seam that later enables an outbox/queue without reshaping
the core.

All events are frozen and ``kw_only`` so subclasses can add required fields
without dataclass default-ordering problems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.value_objects.memory_type import MemoryType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base class: every event carries an id and an occurrence timestamp."""

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, kw_only=True)
class MemoryCreated(DomainEvent):
    memory_id: UUID
    user_id: UUID
    memory_type: MemoryType


@dataclass(frozen=True, kw_only=True)
class MemoryUpdated(DomainEvent):
    memory_id: UUID
    user_id: UUID
    version: int
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class MemoryArchived(DomainEvent):
    memory_id: UUID
    user_id: UUID


@dataclass(frozen=True, kw_only=True)
class MemoryDeleted(DomainEvent):
    memory_id: UUID
    user_id: UUID


@dataclass(frozen=True, kw_only=True)
class MemoryPromoted(DomainEvent):
    memory_id: UUID
    user_id: UUID
    total_score: float

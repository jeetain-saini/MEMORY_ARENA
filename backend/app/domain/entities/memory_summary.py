"""MemorySummary — a rolling, derived summary of a memory scope.

A summary is a **derived artifact**: it condenses a user's memories of one scope
(PROJECT / GOAL / EXPERIENCE) into a single rolling text. It never replaces or
mutates the source memories — it is regenerable from them at any time, stored
separately, versioned, and carries provenance (the ids it was built from).

Pure Python: stdlib + sibling domain modules. No persistence, no frameworks.
Unlike ``Memory`` it records no domain events — summaries are downstream of
memory changes, not a source of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.value_objects.memory_type import MemoryType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemorySummary:
    user_id: UUID
    scope: MemoryType
    summary_text: str
    source_memory_ids: list[UUID] = field(default_factory=list)
    source_count: int = 0
    id: UUID = field(default_factory=uuid4)
    version: int = 1
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        scope: MemoryType,
        summary_text: str,
        source_memory_ids: list[UUID],
    ) -> "MemorySummary":
        return cls(
            user_id=user_id,
            scope=scope,
            summary_text=summary_text,
            source_memory_ids=list(source_memory_ids),
            source_count=len(source_memory_ids),
        )

    def revise(self, *, summary_text: str, source_memory_ids: list[UUID]) -> bool:
        """Update the summary in place; bump ``version`` only when text changes.

        Provenance and ``updated_at`` always refresh; the version increments only
        on a content change, so identical re-runs are idempotent (no churn).
        Returns whether the text actually changed.
        """
        changed = summary_text != self.summary_text
        self.summary_text = summary_text
        self.source_memory_ids = list(source_memory_ids)
        self.source_count = len(source_memory_ids)
        self.updated_at = _utcnow()
        if changed:
            self.version += 1
        return changed

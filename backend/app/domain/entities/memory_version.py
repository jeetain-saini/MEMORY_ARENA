"""MemoryVersion — an immutable historical snapshot of a Memory.

Each edit to a Memory can be preceded by capturing a version, giving an
append-only history that powers auditing and rollback. Versions are frozen: a
snapshot of the past must never change. The version does NOT import Memory at
runtime (only for type-checking) to keep the dependency direction clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime dependency
    from app.domain.entities.memory import Memory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MemoryVersion:
    """A point-in-time copy of a memory's mutable state."""

    memory_id: UUID
    version_number: int
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    metadata: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def capture(cls, memory: "Memory", *, reason: str | None = None) -> "MemoryVersion":
        """Snapshot the current state of ``memory`` as a new version record."""
        return cls(
            memory_id=memory.id,
            version_number=memory.version,
            content=memory.content,
            memory_type=memory.memory_type,
            status=memory.status,
            metadata=dict(memory.metadata),
            reason=reason,
        )

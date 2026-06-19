"""MemoryStatus — the lifecycle state of a memory, with legal transitions.

The status is a value object that also owns the rule for *which* state changes
are allowed. Encoding the transition table here (rather than scattering `if`
checks across entities and services) makes the lifecycle a single, testable
source of truth.
"""

from __future__ import annotations

from enum import Enum


class MemoryStatus(str, Enum):
    """Where a memory sits in its lifecycle."""

    ACTIVE = "active"       # Live and retrievable.
    ARCHIVED = "archived"   # Retained for history, excluded from default retrieval.
    DELETED = "deleted"     # Tombstoned; terminal.

    def can_transition_to(self, target: "MemoryStatus") -> bool:
        """Return True if moving from this status to ``target`` is permitted."""
        return target in _ALLOWED_TRANSITIONS[self]


# Allowed transitions. DELETED is terminal. ARCHIVED -> ACTIVE supports restore.
_ALLOWED_TRANSITIONS: dict[MemoryStatus, set[MemoryStatus]] = {
    MemoryStatus.ACTIVE: {MemoryStatus.ARCHIVED, MemoryStatus.DELETED},
    MemoryStatus.ARCHIVED: {MemoryStatus.ACTIVE, MemoryStatus.DELETED},
    MemoryStatus.DELETED: set(),
}

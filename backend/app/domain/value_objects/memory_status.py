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
    ARCHIVED = "archived"       # Retained for history, excluded from retrieval.
    SUPERSEDED = "superseded"   # Replaced by a newer memory (contradiction resolution).
    FORGOTTEN = "forgotten"     # Aged out by the forgetting engine; hidden, not deleted.
    DELETED = "deleted"         # Tombstoned; terminal.

    def can_transition_to(self, target: "MemoryStatus") -> bool:
        """Return True if moving from this status to ``target`` is permitted."""
        return target in _ALLOWED_TRANSITIONS[self]


#: Statuses returned by default retrieval; everything else is hidden (Stage 17).
RETRIEVABLE_STATUSES: frozenset[MemoryStatus] = frozenset({MemoryStatus.ACTIVE})


# Allowed transitions. DELETED is terminal. ARCHIVED/SUPERSEDED/FORGOTTEN -> ACTIVE
# supports restore (audit/version history is always preserved).
_ALLOWED_TRANSITIONS: dict[MemoryStatus, set[MemoryStatus]] = {
    MemoryStatus.ACTIVE: {
        MemoryStatus.ARCHIVED,
        MemoryStatus.SUPERSEDED,
        MemoryStatus.FORGOTTEN,
        MemoryStatus.DELETED,
    },
    MemoryStatus.ARCHIVED: {MemoryStatus.ACTIVE, MemoryStatus.FORGOTTEN, MemoryStatus.DELETED},
    MemoryStatus.SUPERSEDED: {MemoryStatus.ACTIVE, MemoryStatus.FORGOTTEN, MemoryStatus.DELETED},
    MemoryStatus.FORGOTTEN: {MemoryStatus.ACTIVE, MemoryStatus.DELETED},
    MemoryStatus.DELETED: set(),
}

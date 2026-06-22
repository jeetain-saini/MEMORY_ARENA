"""Memory — the aggregate root of MemoryArena's domain.

A Memory owns its identity, content, lifecycle status, evolving score, and the
domain events its behavior produces. All state changes go through methods that
enforce invariants (legal status transitions, non-empty content) and record the
corresponding domain event. Callers pull events via ``pull_events`` after the
unit of work succeeds.

Pure Python only: standard library + sibling domain modules. No persistence,
no frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.domain.entities.memory_score import MemoryScore
from app.domain.events.memory_events import (
    DomainEvent,
    MemoryArchived,
    MemoryCreated,
    MemoryDecayed,
    MemoryDeleted,
    MemoryForgotten,
    MemoryPromoted,
    MemoryReinforced,
    MemorySuperseded,
    MemoryUpdated,
)
from app.domain.exceptions.errors import InvalidMemoryStateError, MemoryValidationError
from app.domain.value_objects.memory_category import MemoryCategory, default_category
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Memory:
    """A single unit of remembered knowledge for a user."""

    user_id: UUID
    content: str
    memory_type: MemoryType
    id: UUID = field(default_factory=uuid4)
    status: MemoryStatus = MemoryStatus.ACTIVE
    score: MemoryScore = field(default_factory=MemoryScore.neutral)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    is_promoted: bool = False
    priority: int = 0
    # Stage 17: episodic vs semantic. None -> derive from memory_type at init.
    category: MemoryCategory | None = None
    # Stage 17: retrieval-frequency tracking (drives importance + forgetting).
    retrieval_count: int = 0
    last_retrieved_at: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    # Pending domain events; excluded from equality/repr — they are transient.
    _events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise MemoryValidationError("Memory content must not be empty.")
        if self.category is None:
            self.category = default_category(self.memory_type)

    # -- Factory ------------------------------------------------------------
    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        content: str,
        memory_type: MemoryType,
        metadata: dict[str, Any] | None = None,
        score: MemoryScore | None = None,
    ) -> "Memory":
        """Create a new ACTIVE memory and record a MemoryCreated event."""
        memory = cls(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            metadata=dict(metadata or {}),
            score=score or MemoryScore.neutral(),
        )
        memory._record(
            MemoryCreated(
                memory_id=memory.id,
                user_id=memory.user_id,
                memory_type=memory.memory_type,
            )
        )
        return memory

    # -- Behavior (state transitions) --------------------------------------
    def update_content(
        self,
        new_content: str,
        *,
        metadata: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> None:
        """Edit content/metadata, bump the version, and record MemoryUpdated."""
        self._ensure_mutable()
        if not new_content or not new_content.strip():
            raise MemoryValidationError("Memory content must not be empty.")
        self.content = new_content
        if metadata is not None:
            self.metadata = dict(metadata)
        self.version += 1
        self._touch()
        self._record(
            MemoryUpdated(
                memory_id=self.id, user_id=self.user_id, version=self.version, reason=reason
            )
        )

    def reinforce(self, step: float | None = None) -> None:
        """Strengthen the memory from a successful reuse (frequency + utility).

        Counts as activity, so ``updated_at`` is refreshed and a
        ``MemoryReinforced`` event is recorded.
        """
        self._ensure_mutable()
        self.score = self.score.reinforced(step)
        self._touch()
        self._record(
            MemoryReinforced(
                memory_id=self.id,
                user_id=self.user_id,
                frequency=self.score.frequency,
                utility=self.score.utility,
                total_score=self.score.calculate_total_score(),
            )
        )

    def decay(self, recency_factor: float) -> None:
        """Apply time-based recency decay (a system recalculation, not a use).

        Deliberately does NOT refresh ``updated_at`` — decay must not look like
        activity, or it would defeat idle-based archival.
        """
        self._ensure_mutable()
        self.score = self.score.decayed(recency_factor)
        self._record(
            MemoryDecayed(
                memory_id=self.id,
                user_id=self.user_id,
                recency=self.score.recency,
                total_score=self.score.calculate_total_score(),
            )
        )

    def promote(self, *, threshold: float | None = None) -> None:
        """Promote a high-value memory: keep it ACTIVE, flag it, raise priority."""
        if self.status is not MemoryStatus.ACTIVE:
            raise InvalidMemoryStateError("Only an ACTIVE memory can be promoted.")
        if self.is_promoted:
            raise InvalidMemoryStateError("Memory is already promoted.")
        if not self.score.is_promotable(threshold):
            raise InvalidMemoryStateError(
                "Memory score is below the promotion threshold."
            )
        self.is_promoted = True
        self.priority += 1
        self._touch()
        self._record(
            MemoryPromoted(
                memory_id=self.id,
                user_id=self.user_id,
                total_score=self.score.calculate_total_score(),
                priority=self.priority,
            )
        )

    def archive(self) -> None:
        """Move the memory to ARCHIVED."""
        self._transition_to(MemoryStatus.ARCHIVED)
        self._record(MemoryArchived(memory_id=self.id, user_id=self.user_id))

    def restore(self) -> None:
        """Bring an ARCHIVED/SUPERSEDED/FORGOTTEN memory back to ACTIVE."""
        self._transition_to(MemoryStatus.ACTIVE)

    def supersede(self, *, superseded_by_id: UUID) -> None:
        """Mark this memory as replaced by a newer one (status -> SUPERSEDED)."""
        self._transition_to(MemoryStatus.SUPERSEDED)
        self._record(
            MemorySuperseded(
                memory_id=self.id, superseded_by_id=superseded_by_id, user_id=self.user_id
            )
        )

    def forget(self, *, reason: str | None = None) -> None:
        """Age the memory out (status -> FORGOTTEN); hidden from retrieval, kept."""
        self._transition_to(MemoryStatus.FORGOTTEN)
        self._record(MemoryForgotten(memory_id=self.id, user_id=self.user_id, reason=reason))

    def record_retrieval(self, *, now: datetime | None = None) -> None:
        """Note that retrieval returned this memory (lightweight; no event/version).

        Bumps ``retrieval_count`` and ``last_retrieved_at`` only. Deliberately
        does not touch ``updated_at`` or emit an event — it is a read-side signal
        for importance/forgetting, not a content change.
        """
        self.retrieval_count += 1
        self.last_retrieved_at = now or _utcnow()

    def reclassify(self, category: MemoryCategory) -> None:
        """Override the memory's category (e.g. episodic -> semantic on promotion)."""
        self.category = category

    def delete(self) -> None:
        """Tombstone the memory (terminal)."""
        self._transition_to(MemoryStatus.DELETED)
        self._record(MemoryDeleted(memory_id=self.id, user_id=self.user_id))

    def rollback_to(self, version: "MemoryVersion") -> None:
        """Restore content/type/metadata from a historical version snapshot."""
        self._ensure_mutable()
        if version.memory_id != self.id:
            raise InvalidMemoryStateError("Version does not belong to this memory.")
        self.content = version.content
        self.memory_type = version.memory_type
        self.metadata = dict(version.metadata)
        self.version += 1
        self._touch()
        self._record(
            MemoryUpdated(
                memory_id=self.id,
                user_id=self.user_id,
                version=self.version,
                reason=f"rollback_to_v{version.version_number}",
            )
        )

    # -- Maintenance bookkeeping -------------------------------------------
    #: Reserved metadata key holding maintenance markers (e.g. decay periods).
    _MAINTENANCE_KEY = "_maintenance"

    def stamp_maintenance(self, marker: str, value: str) -> None:
        """Record a maintenance marker (e.g. the last decay period) in metadata.

        Pure bookkeeping for idempotent/resumable maintenance sweeps: it records
        *that* a periodic job processed this memory, without changing the
        memory's meaning. It records **no domain event** and does not touch
        ``updated_at`` (so it never looks like activity to archival).
        """
        markers = self.metadata.get(self._MAINTENANCE_KEY)
        if not isinstance(markers, dict):
            markers = {}
        markers[marker] = value
        self.metadata[self._MAINTENANCE_KEY] = markers

    def was_swept(self, marker: str, value: str) -> bool:
        """Whether this memory already carries ``marker == value``."""
        markers = self.metadata.get(self._MAINTENANCE_KEY)
        return isinstance(markers, dict) and markers.get(marker) == value

    # -- Derived ------------------------------------------------------------
    @property
    def total_score(self) -> float:
        return self.score.calculate_total_score()

    # -- Event handling -----------------------------------------------------
    def pull_events(self) -> list[DomainEvent]:
        """Return and clear pending events (call after the unit of work commits)."""
        events = list(self._events)
        self._events.clear()
        return events

    # -- Internals ----------------------------------------------------------
    def _transition_to(self, target: MemoryStatus) -> None:
        if not self.status.can_transition_to(target):
            raise InvalidMemoryStateError(
                f"Illegal transition {self.status.value} -> {target.value}."
            )
        self.status = target
        self._touch()

    def _ensure_mutable(self) -> None:
        if self.status is MemoryStatus.DELETED:
            raise InvalidMemoryStateError("A DELETED memory cannot be modified.")

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def _record(self, event: DomainEvent) -> None:
        self._events.append(event)


# Imported at end to avoid a circular import at module load (type-only use above).
from app.domain.entities.memory_version import MemoryVersion  # noqa: E402

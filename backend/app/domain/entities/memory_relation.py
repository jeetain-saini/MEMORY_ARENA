"""MemoryRelation — a typed, directed edge between two memories.

The building block of MemoryArena's memory graph. A relation is its own entity
(it has identity and a strength) rather than a mere attribute, because edges
themselves can be reinforced, weakened, or contradicted over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.domain.exceptions.errors import InvalidRelationError
from app.domain.value_objects.relation_type import RelationType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryRelation:
    """A directed edge ``source --relation_type--> target`` with a strength."""

    source_memory_id: UUID
    target_memory_id: UUID
    relation_type: RelationType
    weight: float = 1.0  # Edge strength in [0.0, 1.0]; reinforced/decayed over time.
    metadata: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.source_memory_id == self.target_memory_id:
            raise InvalidRelationError("A memory cannot relate to itself.")
        if not 0.0 <= self.weight <= 1.0:
            raise InvalidRelationError("Relation weight must be within [0.0, 1.0].")

    @classmethod
    def create(
        cls,
        *,
        source_memory_id: UUID,
        target_memory_id: UUID,
        relation_type: RelationType,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> "MemoryRelation":
        return cls(
            source_memory_id=source_memory_id,
            target_memory_id=target_memory_id,
            relation_type=relation_type,
            weight=weight,
            metadata=dict(metadata or {}),
        )

"""Mapper tests — domain <-> ORM round-trips (no database required)."""

from __future__ import annotations

from uuid import uuid4

from app.domain.entities.memory import Memory
from app.domain.entities.memory_relation import MemoryRelation
from app.domain.entities.memory_score import MemoryScore
from app.domain.entities.memory_version import MemoryVersion
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.domain.value_objects.relation_type import RelationType
from app.infrastructure.database.mappers import (
    memory_to_model,
    model_to_memory,
    model_to_relation,
    model_to_version,
    relation_to_model,
    version_to_model,
)


def test_memory_round_trip_preserves_fields() -> None:
    memory = Memory.create(
        user_id=uuid4(),
        content="The user prefers dark mode.",
        memory_type=MemoryType.PREFERENCE,
        metadata={"source": "chat"},
        score=MemoryScore(importance=0.8, utility=0.6, frequency=0.4, recency=1.0, confidence=0.5),
    )
    model = memory_to_model(memory)
    assert model.memory_type == "preference"
    assert model.status == "active"
    assert model.meta == {"source": "chat"}

    restored = model_to_memory(model)
    assert restored.id == memory.id
    assert restored.user_id == memory.user_id
    assert restored.content == memory.content
    assert restored.memory_type is MemoryType.PREFERENCE
    assert restored.status is MemoryStatus.ACTIVE
    assert restored.metadata == {"source": "chat"}
    assert restored.score.calculate_total_score() == memory.score.calculate_total_score()
    # Rehydration must not emit creation events.
    assert restored.pull_events() == []


def test_relation_round_trip() -> None:
    relation = MemoryRelation.create(
        source_memory_id=uuid4(),
        target_memory_id=uuid4(),
        relation_type=RelationType.DERIVED_FROM,
        weight=0.5,
    )
    restored = model_to_relation(relation_to_model(relation))
    assert restored.id == relation.id
    assert restored.relation_type is RelationType.DERIVED_FROM
    assert restored.weight == 0.5


def test_version_round_trip() -> None:
    memory = Memory.create(user_id=uuid4(), content="Original.", memory_type=MemoryType.FACT)
    version = MemoryVersion.capture(memory, reason="pre-edit")
    restored = model_to_version(version_to_model(version))
    assert restored.memory_id == memory.id
    assert restored.version_number == 1
    assert restored.content == "Original."
    assert restored.memory_type is MemoryType.FACT
    assert restored.reason == "pre-edit"

"""Domain tests for MemoryRelation — graph edges between memories."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.entities.memory_relation import MemoryRelation
from app.domain.exceptions.errors import InvalidRelationError
from app.domain.value_objects.relation_type import RelationType


def test_create_relation() -> None:
    source, target = uuid4(), uuid4()
    relation = MemoryRelation.create(
        source_memory_id=source,
        target_memory_id=target,
        relation_type=RelationType.DEPENDS_ON,
    )
    assert relation.source_memory_id == source
    assert relation.target_memory_id == target
    assert relation.relation_type is RelationType.DEPENDS_ON
    assert relation.weight == 1.0


def test_self_relation_is_rejected() -> None:
    same = uuid4()
    with pytest.raises(InvalidRelationError):
        MemoryRelation.create(
            source_memory_id=same,
            target_memory_id=same,
            relation_type=RelationType.RELATED_TO,
        )


def test_weight_must_be_normalized() -> None:
    with pytest.raises(InvalidRelationError):
        MemoryRelation.create(
            source_memory_id=uuid4(),
            target_memory_id=uuid4(),
            relation_type=RelationType.REINFORCES,
            weight=1.5,
        )

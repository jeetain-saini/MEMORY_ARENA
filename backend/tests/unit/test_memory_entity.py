"""Domain tests for the Memory aggregate — transitions, events, promotion."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.events.memory_events import (
    MemoryArchived,
    MemoryCreated,
    MemoryDeleted,
    MemoryPromoted,
    MemoryUpdated,
)
from app.domain.exceptions.errors import InvalidMemoryStateError, MemoryValidationError
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


def _new_memory(**overrides: object) -> Memory:
    params = dict(user_id=uuid4(), content="The user prefers dark mode.", memory_type=MemoryType.PREFERENCE)
    params.update(overrides)
    return Memory.create(**params)  # type: ignore[arg-type]


def test_create_emits_memory_created_event() -> None:
    memory = _new_memory()
    assert memory.status is MemoryStatus.ACTIVE
    assert memory.version == 1
    events = memory.pull_events()
    assert len(events) == 1 and isinstance(events[0], MemoryCreated)
    # Events are cleared after pulling.
    assert memory.pull_events() == []


def test_empty_content_is_rejected() -> None:
    with pytest.raises(MemoryValidationError):
        _new_memory(content="   ")


def test_update_content_bumps_version_and_emits_event() -> None:
    memory = _new_memory()
    memory.pull_events()  # clear creation event
    memory.update_content("The user now prefers light mode.", reason="correction")
    assert memory.version == 2
    events = memory.pull_events()
    assert isinstance(events[0], MemoryUpdated)
    assert events[0].reason == "correction"


def test_archive_then_delete_transitions() -> None:
    memory = _new_memory()
    memory.archive()
    assert memory.status is MemoryStatus.ARCHIVED
    memory.delete()
    assert memory.status is MemoryStatus.DELETED
    types = [type(e) for e in memory.pull_events()]
    assert MemoryArchived in types and MemoryDeleted in types


def test_illegal_transition_raises() -> None:
    memory = _new_memory()
    memory.delete()
    with pytest.raises(InvalidMemoryStateError):
        memory.archive()  # DELETED is terminal


def test_deleted_memory_cannot_be_edited() -> None:
    memory = _new_memory()
    memory.delete()
    with pytest.raises(InvalidMemoryStateError):
        memory.update_content("anything")


def test_promote_requires_sufficient_score() -> None:
    weak = _new_memory(score=MemoryScore(importance=0, utility=0, frequency=0, recency=0, confidence=0))
    with pytest.raises(InvalidMemoryStateError):
        weak.promote()

    strong = _new_memory(
        score=MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1)
    )
    strong.pull_events()
    strong.promote()
    assert strong.is_promoted is True
    assert isinstance(strong.pull_events()[0], MemoryPromoted)


def test_restore_archived_memory() -> None:
    memory = _new_memory()
    memory.archive()
    memory.restore()
    assert memory.status is MemoryStatus.ACTIVE

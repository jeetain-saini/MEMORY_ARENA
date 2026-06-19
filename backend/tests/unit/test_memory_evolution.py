"""Domain tests for memory evolution behaviors (reinforce / decay / promote)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.events.memory_events import (
    MemoryDecayed,
    MemoryPromoted,
    MemoryReinforced,
)
from app.domain.exceptions.errors import InvalidMemoryStateError
from app.domain.value_objects.memory_type import MemoryType


def _memory(score: MemoryScore | None = None) -> Memory:
    return Memory.create(
        user_id=uuid4(), content="x", memory_type=MemoryType.FACT, score=score
    )


def test_reinforce_raises_frequency_and_utility_and_emits_event() -> None:
    memory = _memory(MemoryScore(frequency=0.1, utility=0.2))
    memory.pull_events()
    memory.reinforce(step=0.1)
    assert memory.score.frequency == pytest.approx(0.2)
    assert memory.score.utility == pytest.approx(0.3)
    assert memory.score.recency == 1.0
    events = memory.pull_events()
    assert isinstance(events[0], MemoryReinforced)


def test_reinforce_refreshes_updated_at() -> None:
    memory = _memory()
    memory.updated_at = datetime.now(timezone.utc) - timedelta(days=10)
    before = memory.updated_at
    memory.reinforce()
    assert memory.updated_at > before


def test_decay_reduces_recency_and_emits_event_without_touching_updated_at() -> None:
    memory = _memory(MemoryScore(recency=1.0))
    stale = datetime.now(timezone.utc) - timedelta(days=10)
    memory.updated_at = stale
    memory.pull_events()
    memory.decay(0.5)
    assert memory.score.recency == pytest.approx(0.5)
    assert memory.updated_at == stale  # decay is not activity
    assert isinstance(memory.pull_events()[0], MemoryDecayed)


def test_decay_on_deleted_memory_raises() -> None:
    memory = _memory()
    memory.delete()
    with pytest.raises(InvalidMemoryStateError):
        memory.decay(0.5)


def test_promote_increments_priority_and_emits_event() -> None:
    memory = _memory(MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1))
    memory.pull_events()
    memory.promote()
    assert memory.is_promoted is True
    assert memory.priority == 1
    event = memory.pull_events()[0]
    assert isinstance(event, MemoryPromoted)
    assert event.priority == 1


def test_promote_twice_raises() -> None:
    memory = _memory(MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1))
    memory.promote()
    with pytest.raises(InvalidMemoryStateError):
        memory.promote()

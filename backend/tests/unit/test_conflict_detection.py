"""Unit tests for ConflictDetector."""

from __future__ import annotations

from uuid import uuid4

from app.application.dto.context_dto import ContextMemory
from app.application.services.context.conflict_detector import ConflictDetector
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


def _cm(content: str) -> ContextMemory:
    return ContextMemory(
        memory_id=uuid4(), content=content, memory_type=MemoryType.FACT,
        status=MemoryStatus.ACTIVE, score=0.5, tokens=5,
    )


def test_detects_negation_contradiction() -> None:
    conflicts = ConflictDetector().detect([_cm("I use Python"), _cm("I no longer use Python")])
    assert len(conflicts) == 1
    assert conflicts[0].reason == "negation_contradiction"


def test_no_conflict_when_both_positive() -> None:
    assert ConflictDetector().detect([_cm("I use Python"), _cm("I use Python daily")]) == []


def test_no_conflict_when_both_negated() -> None:
    # Both negated about the same subject => they agree, not contradict.
    assert ConflictDetector().detect([_cm("I do not use Python"), _cm("I never use Python")]) == []


def test_no_conflict_for_unrelated_topics() -> None:
    assert ConflictDetector().detect([_cm("I love tea"), _cm("I do not drive cars")]) == []


def test_single_memory_has_no_conflicts() -> None:
    assert ConflictDetector().detect([_cm("I use Python")]) == []

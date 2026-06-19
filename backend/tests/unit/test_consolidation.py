"""Unit tests for MemoryConsolidationService."""

from __future__ import annotations

from uuid import uuid4

from app.application.dto.context_dto import ContextMemory
from app.application.services.context.consolidation_service import MemoryConsolidationService
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


def _cm(content: str, score: float) -> ContextMemory:
    return ContextMemory(
        memory_id=uuid4(), content=content, memory_type=MemoryType.FACT,
        status=MemoryStatus.ACTIVE, score=score, tokens=5,
    )


def test_merges_duplicates_keeping_highest_score() -> None:
    low = _cm("the sky is blue", 0.3)
    high = _cm("the sky is blue", 0.9)
    result = MemoryConsolidationService().consolidate([low, high])
    assert len(result.consolidated) == 1
    assert result.consolidated[0].memory_id == high.memory_id
    assert result.removed[0].memory_id == low.memory_id
    assert result.records[0].kept_memory_id == high.memory_id
    assert low.memory_id in result.records[0].removed_memory_ids


def test_distinct_memories_are_all_kept() -> None:
    result = MemoryConsolidationService().consolidate(
        [_cm("apples are red", 0.5), _cm("bananas are yellow", 0.4)]
    )
    assert len(result.consolidated) == 2
    assert result.removed == []
    assert result.records == []


def test_reason_is_duplicate() -> None:
    result = MemoryConsolidationService().consolidate(
        [_cm("identical text here", 0.6), _cm("identical text here", 0.5)]
    )
    assert result.removed[0].reason == "duplicate"


def test_empty_input() -> None:
    result = MemoryConsolidationService().consolidate([])
    assert result.consolidated == [] and result.removed == []

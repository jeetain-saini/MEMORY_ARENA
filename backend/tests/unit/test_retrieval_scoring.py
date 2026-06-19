"""Unit tests for retrieval scoring helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.application.dto.retrieval_dto import RetrievalFilters
from app.application.services.retrieval.config import RetrievalConfig
from app.application.services.retrieval.scoring import (
    cosine_similarity,
    memory_boost_score,
    passes_filters,
    recency_score,
)
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType

NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)
CFG = RetrievalConfig()


def test_cosine_identical_is_one() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_opposite_is_negative_one() -> None:
    assert cosine_similarity([1.0, 1.0], [-1.0, -1.0]) == pytest.approx(-1.0)


def test_cosine_handles_degenerate() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_recency_fresh_is_one_and_decays() -> None:
    assert recency_score(NOW, NOW, 30.0) == pytest.approx(1.0)
    assert recency_score(NOW - timedelta(days=30), NOW, 30.0) == pytest.approx(0.5)
    assert recency_score(NOW - timedelta(days=60), NOW, 30.0) < 0.3


def _memory(score: MemoryScore, *, promoted=False, priority=0, status=MemoryStatus.ACTIVE) -> Memory:
    m = Memory(user_id=uuid4(), content="x", memory_type=MemoryType.FACT, score=score)
    m.is_promoted = promoted
    m.priority = priority
    m.status = status
    return m


def test_memory_boost_in_range_and_promotion_helps() -> None:
    low = _memory(MemoryScore(importance=0, utility=0, frequency=0, recency=0, confidence=0))
    high = _memory(
        MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1),
        promoted=True, priority=5,
    )
    low_score = memory_boost_score(low, CFG)
    high_score = memory_boost_score(high, CFG)
    assert 0.0 <= low_score <= 1.0
    assert 0.0 <= high_score <= 1.0
    assert high_score > low_score


def test_memory_boost_priority_increases_score() -> None:
    base = _memory(MemoryScore(importance=0.5, utility=0.5, frequency=0.5))
    prioritized = _memory(MemoryScore(importance=0.5, utility=0.5, frequency=0.5), priority=5)
    assert memory_boost_score(prioritized, CFG) > memory_boost_score(base, CFG)


def test_passes_filters_defaults_to_active() -> None:
    active = _memory(MemoryScore(), status=MemoryStatus.ACTIVE)
    archived = _memory(MemoryScore(), status=MemoryStatus.ARCHIVED)
    assert passes_filters(active, RetrievalFilters()) is True
    assert passes_filters(archived, RetrievalFilters()) is False
    assert passes_filters(archived, RetrievalFilters(statuses=[MemoryStatus.ARCHIVED])) is True


def test_passes_filters_by_type() -> None:
    fact = _memory(MemoryScore())
    assert passes_filters(fact, RetrievalFilters(memory_types=[MemoryType.GOAL])) is False
    assert passes_filters(fact, RetrievalFilters(memory_types=[MemoryType.FACT])) is True

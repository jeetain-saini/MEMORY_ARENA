"""Domain tests for MemoryScore — the weighted, normalized relevance signal."""

from __future__ import annotations

import pytest

from app.domain.entities.memory_score import MemoryScore
from app.domain.exceptions.errors import InvalidScoreError


def test_weights_sum_to_one() -> None:
    total = (
        MemoryScore.WEIGHT_IMPORTANCE
        + MemoryScore.WEIGHT_UTILITY
        + MemoryScore.WEIGHT_FREQUENCY
        + MemoryScore.WEIGHT_RECENCY
        + MemoryScore.WEIGHT_CONFIDENCE
    )
    assert total == pytest.approx(1.0)


def test_all_max_scores_to_one() -> None:
    score = MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1)
    assert score.calculate_total_score() == pytest.approx(1.0)


def test_known_weighted_combination() -> None:
    # 0.30*0.8 + 0.25*0.6 + 0.20*0.4 + 0.15*1.0 + 0.10*0.5 = 0.67
    score = MemoryScore(importance=0.8, utility=0.6, frequency=0.4, recency=1.0, confidence=0.5)
    assert score.calculate_total_score() == pytest.approx(0.67)


def test_score_is_normalized_between_zero_and_one() -> None:
    score = MemoryScore(importance=0, utility=0, frequency=0, recency=0, confidence=0)
    assert score.calculate_total_score() == 0.0


def test_out_of_range_component_rejected() -> None:
    with pytest.raises(InvalidScoreError):
        MemoryScore(importance=1.5)


def test_reinforce_raises_frequency_and_resets_recency() -> None:
    score = MemoryScore(frequency=0.2, recency=0.3)
    reinforced = score.reinforced(step=0.1)
    assert reinforced.frequency == pytest.approx(0.3)
    assert reinforced.recency == 1.0
    # Original is immutable / untouched.
    assert score.frequency == pytest.approx(0.2)


def test_is_promotable_respects_threshold() -> None:
    high = MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1)
    low = MemoryScore(importance=0, utility=0, frequency=0, recency=0, confidence=0)
    assert high.is_promotable() is True
    assert low.is_promotable() is False

"""Tests for the configurable recency-decay strategies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.application.services.decay_strategies import (
    ExponentialDecayStrategy,
    LinearDecayStrategy,
)
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType

NOW = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _memory_idle(days: float) -> Memory:
    m = Memory.create(user_id=uuid4(), content="x", memory_type=MemoryType.FACT)
    m.updated_at = NOW - timedelta(days=days)
    return m


def test_exponential_no_age_is_full() -> None:
    assert ExponentialDecayStrategy(7).compute_factor(_memory_idle(0), NOW) == pytest.approx(1.0)


def test_exponential_at_half_life_is_half() -> None:
    assert ExponentialDecayStrategy(7).compute_factor(_memory_idle(7), NOW) == pytest.approx(0.5)


def test_exponential_decreases_with_age() -> None:
    strat = ExponentialDecayStrategy(7)
    f7 = strat.compute_factor(_memory_idle(7), NOW)
    f14 = strat.compute_factor(_memory_idle(14), NOW)
    assert f14 < f7


def test_exponential_rejects_nonpositive_half_life() -> None:
    with pytest.raises(ValueError):
        ExponentialDecayStrategy(0)


def test_linear_no_age_is_full() -> None:
    assert LinearDecayStrategy(0.1).compute_factor(_memory_idle(0), NOW) == pytest.approx(1.0)


def test_linear_reduces_over_time() -> None:
    assert LinearDecayStrategy(0.1).compute_factor(_memory_idle(5), NOW) == pytest.approx(0.5)


def test_linear_clamps_at_zero() -> None:
    assert LinearDecayStrategy(0.1).compute_factor(_memory_idle(100), NOW) == 0.0


def test_linear_rejects_bad_rate() -> None:
    with pytest.raises(ValueError):
        LinearDecayStrategy(2.0)

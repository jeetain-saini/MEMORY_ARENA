"""Configurable recency-decay strategies.

A decay strategy answers one question: given a memory and the current time, by
what factor in [0, 1] should its recency be multiplied? Different deployments
can choose different curves (exponential half-life, linear bleed-off) without
changing the domain or the intelligence service — the strategy is injected.

Decay is driven by ``updated_at`` (the timestamp of the last *activity*:
creation, edit, reinforcement). Because ``Memory.decay`` deliberately does not
refresh ``updated_at``, repeated sweeps keep measuring true idle age.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.domain.entities.memory import Memory


def _age_days(memory: Memory, now: datetime) -> float:
    reference = memory.updated_at
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    seconds = (now - reference).total_seconds()
    return max(0.0, seconds / 86_400.0)


class DecayStrategy(ABC):
    """Computes the recency multiplier to apply to a memory."""

    @abstractmethod
    def compute_factor(self, memory: Memory, now: datetime) -> float:
        """Return a recency multiplier in [0.0, 1.0]."""


class ExponentialDecayStrategy(DecayStrategy):
    """Half-life decay: recency halves every ``half_life_days`` of inactivity."""

    def __init__(self, half_life_days: float = 7.0) -> None:
        if half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        self.half_life_days = half_life_days

    def compute_factor(self, memory: Memory, now: datetime) -> float:
        age = _age_days(memory, now)
        factor = 0.5 ** (age / self.half_life_days)
        return min(1.0, max(0.0, factor))


class LinearDecayStrategy(DecayStrategy):
    """Linear decay: recency loses ``rate_per_day`` per idle day (clamped at 0)."""

    def __init__(self, rate_per_day: float = 0.05) -> None:
        if not 0.0 <= rate_per_day <= 1.0:
            raise ValueError("rate_per_day must be within [0.0, 1.0]")
        self.rate_per_day = rate_per_day

    def compute_factor(self, memory: Memory, now: datetime) -> float:
        age = _age_days(memory, now)
        return min(1.0, max(0.0, 1.0 - self.rate_per_day * age))

"""Tunable thresholds for the Memory Intelligence Engine.

Centralizes the policy knobs so reinforcement strength, the promotion bar, and
the archival criteria can be tuned (per environment, or later per tenant)
without touching the evaluation logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntelligenceConfig:
    # Reinforcement: how much each successful reuse raises frequency & utility.
    reinforcement_step: float = 0.10
    # Promotion: minimum total_score required to promote.
    promotion_threshold: float = 0.65
    # Archival: archive when total_score is below this AND idle long enough.
    archival_score_threshold: float = 0.30
    archival_max_idle_days: int = 30

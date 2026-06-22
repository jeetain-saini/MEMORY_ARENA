"""ImportanceEvolutionService — dynamic importance updates (Stage 17 Area 4).

Deterministic, configurable blend of signals into a memory's importance:

  importance' = w_base*importance + w_freq*freq + w_central*centrality
              + w_recency*recency + w_contra*contradiction + promotion_bonus

All inputs are normalized to [0, 1] and the result is clamped to [0, 1]. Pure
function over a ``Memory`` plus externally-supplied graph signals — no I/O — so
it is trivially reusable and testable. It returns a new ``MemoryScore`` (the
score value object is immutable) rather than mutating in place.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore


@dataclass(frozen=True)
class ImportanceWeights:
    base: float = 0.45          # inertia: keep most of the prior importance
    frequency: float = 0.20     # how often retrieved
    centrality: float = 0.15    # graph centrality (degree / max-degree)
    recency: float = 0.10       # how recently touched
    contradiction: float = 0.10  # involved in a contradiction -> more salient
    promotion_bonus: float = 0.05  # promoted memories get a small floor lift
    # Retrieval count that maps to a frequency signal of 1.0 (saturating).
    frequency_saturation: int = 10


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


class ImportanceEvolutionService:
    def __init__(self, weights: ImportanceWeights | None = None) -> None:
        self._w = weights or ImportanceWeights()

    def next_importance(
        self,
        memory: Memory,
        *,
        centrality: float = 0.0,
        contradiction_involved: bool = False,
    ) -> float:
        """Return the evolved importance value in [0, 1] (does not mutate)."""
        w = self._w
        freq_signal = _clamp01(memory.retrieval_count / max(1, w.frequency_saturation))
        value = (
            w.base * memory.score.importance
            + w.frequency * freq_signal
            + w.centrality * _clamp01(centrality)
            + w.recency * _clamp01(memory.score.recency)
            + w.contradiction * (1.0 if contradiction_involved else 0.0)
        )
        if memory.is_promoted:
            value += w.promotion_bonus
        return round(_clamp01(value), 6)

    def evolve(
        self,
        memory: Memory,
        *,
        centrality: float = 0.0,
        contradiction_involved: bool = False,
    ) -> MemoryScore:
        """Return a new ``MemoryScore`` with the evolved importance applied."""
        new_importance = self.next_importance(
            memory, centrality=centrality, contradiction_involved=contradiction_involved
        )
        s = memory.score
        return MemoryScore(
            importance=new_importance,
            utility=s.utility,
            frequency=s.frequency,
            recency=s.recency,
            confidence=s.confidence,
        )

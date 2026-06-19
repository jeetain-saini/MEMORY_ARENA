"""MemoryScore — the self-evolving relevance signal of a memory.

A frozen value object holding five normalized [0.0, 1.0] components. The total
score is their fixed weighted sum, which (because the weights sum to 1.0 and
every component is in [0,1]) is itself guaranteed to be normalized in [0,1].

Being immutable, "evolution" is modeled as producing a *new* score
(``reinforced``, ``decayed``) rather than mutating in place — so a score change
is always an explicit, traceable event the owning Memory can react to.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar

from app.domain.exceptions.errors import InvalidScoreError


@dataclass(frozen=True)
class MemoryScore:
    """Five weighted signals that decide how relevant a memory is right now."""

    importance: float = 0.5   # Intrinsic significance (set/learned, slow to change).
    utility: float = 0.5      # How useful it has proven when retrieved.
    frequency: float = 0.0    # How often it is accessed/reinforced.
    recency: float = 1.0      # How recently it was touched (decays over time).
    confidence: float = 0.5   # How sure we are the memory is correct.

    # Weights MUST sum to 1.0 so the total is normalized. (PART 2 spec.)
    WEIGHT_IMPORTANCE: ClassVar[float] = 0.30
    WEIGHT_UTILITY: ClassVar[float] = 0.25
    WEIGHT_FREQUENCY: ClassVar[float] = 0.20
    WEIGHT_RECENCY: ClassVar[float] = 0.15
    WEIGHT_CONFIDENCE: ClassVar[float] = 0.10

    DEFAULT_PROMOTION_THRESHOLD: ClassVar[float] = 0.65
    REINFORCEMENT_STEP: ClassVar[float] = 0.10

    def __post_init__(self) -> None:
        for name in ("importance", "utility", "frequency", "recency", "confidence"):
            value = getattr(self, name)
            if not 0.0 <= float(value) <= 1.0:
                raise InvalidScoreError(f"{name} must be within [0.0, 1.0], got {value!r}")

    def calculate_total_score(self) -> float:
        """Return the normalized weighted total in [0.0, 1.0], rounded to 4 dp."""
        total = (
            self.WEIGHT_IMPORTANCE * self.importance
            + self.WEIGHT_UTILITY * self.utility
            + self.WEIGHT_FREQUENCY * self.frequency
            + self.WEIGHT_RECENCY * self.recency
            + self.WEIGHT_CONFIDENCE * self.confidence
        )
        # Clamp defensively against floating-point drift, then round.
        return round(min(1.0, max(0.0, total)), 4)

    def is_promotable(self, threshold: float | None = None) -> bool:
        """True when the total score meets the promotion threshold."""
        limit = self.DEFAULT_PROMOTION_THRESHOLD if threshold is None else threshold
        return self.calculate_total_score() >= limit

    def reinforced(self, step: float | None = None) -> "MemoryScore":
        """Return a new score reflecting an access/reinforcement.

        Frequency rises by ``step`` (capped at 1.0) and recency resets to fresh.
        """
        delta = self.REINFORCEMENT_STEP if step is None else step
        return replace(
            self,
            frequency=min(1.0, self.frequency + delta),
            recency=1.0,
        )

    def decayed(self, recency_factor: float) -> "MemoryScore":
        """Return a new score with recency multiplied by ``recency_factor``.

        Time-based decay is applied by an external scheduler; the domain only
        defines *how* a decay transforms the value, not *when* it runs.
        """
        if not 0.0 <= recency_factor <= 1.0:
            raise InvalidScoreError("recency_factor must be within [0.0, 1.0]")
        return replace(self, recency=self.recency * recency_factor)

    @classmethod
    def neutral(cls) -> "MemoryScore":
        """A sensible default score for a freshly created memory."""
        return cls()

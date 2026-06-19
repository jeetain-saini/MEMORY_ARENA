"""Analytics DTOs — the shape of aggregated memory statistics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MemoryAnalytics:
    total_memories: int
    active_memories: int
    archived_memories: int
    promoted_memories: int
    average_score: float
    # Bucketed counts of total_score, e.g. {"0.0-0.2": 3, "0.2-0.4": 5, ...}.
    score_distribution: dict[str, int] = field(default_factory=dict)

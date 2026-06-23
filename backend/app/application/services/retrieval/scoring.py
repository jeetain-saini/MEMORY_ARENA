"""Pure scoring helpers for retrieval: similarity, recency, memory boosting.

No I/O — just math over domain objects and vectors. Kept separate so each
signal is independently testable.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.application.dto.retrieval_dto import RetrievalFilters
from app.application.services.retrieval.config import RetrievalConfig
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_status import MemoryStatus


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]; 0 if either vector is degenerate."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def recency_score(updated_at: datetime, now: datetime, half_life_days: float) -> float:
    """Exponential recency in [0, 1]: 1.0 when fresh, halving every half-life."""
    reference = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - reference).total_seconds() / 86_400.0)
    return 0.5 ** (age_days / half_life_days)


def memory_boost_score(memory: Memory, config: RetrievalConfig) -> float:
    """Boost from Memory Intelligence signals, normalized to [0, 1].

    Blends importance/utility/frequency/retrieval-frequency, then adds promotion,
    priority, semantic, and cluster bonuses so evolved, high-value memories rank
    higher. (Stage 17.1: importance evolves from retrieval, and retrieval_count,
    semantic category, and cluster membership now feed ranking.)
    """
    score = memory.score
    denom = (
        config.mem_importance + config.mem_utility + config.mem_frequency + config.mem_retrieval
    )
    base = 0.0
    if denom > 0:
        retrieval_signal = clamp01(memory.retrieval_count / max(1, config.retrieval_saturation))
        base = (
            config.mem_importance * score.importance
            + config.mem_utility * score.utility
            + config.mem_frequency * score.frequency
            + config.mem_retrieval * retrieval_signal
        ) / denom

    boost = config.promotion_bonus if memory.is_promoted else 0.0
    if config.priority_cap > 0:
        boost += config.priority_weight * min(memory.priority, config.priority_cap) / config.priority_cap

    # Stage 17 additive signals (config-gated; default 0.0 -> backward compatible).
    if getattr(memory, "category", None) is MemoryCategory.SEMANTIC:
        boost += config.semantic_bonus
    if memory.metadata.get("cluster_id"):
        boost += config.cluster_bonus

    return clamp01(base + boost)


def passes_filters(memory: Memory, filters: RetrievalFilters) -> bool:
    """Apply retrieval filters. Defaults to ACTIVE-only when no status given."""
    statuses = filters.statuses or [MemoryStatus.ACTIVE]
    if memory.status not in statuses:
        return False
    if filters.memory_types is not None and memory.memory_type not in filters.memory_types:
        return False
    return True


def rank_candidates(
    candidates: list[tuple[Memory, list[float]]],
    query_vector: list[float],
    filters: RetrievalFilters,
    limit: int,
) -> list[tuple[Memory, float]]:
    """Filter + cosine-score + top-k (the brute-force vector ranking).

    The single source of brute-force ranking, shared by ``BruteForceVectorIndex``
    and the repository's non-PostgreSQL ``search_similar`` fallback, so they are
    guaranteed identical (and identical to the pre-Phase-5 ``VectorRetriever``).
    """
    scored = [
        (memory, cosine_similarity(query_vector, vector))
        for memory, vector in candidates
        if passes_filters(memory, filters)
    ]
    scored.sort(key=lambda s: s[1], reverse=True)
    return scored[:limit]

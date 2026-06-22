"""Memory health DTOs (Stage 13).

A tenant-scoped snapshot of how a user's memory corpus is evolving: growth,
promotion/archive rates, a reinforcement proxy, graph density, and summary
coverage. Read-only aggregation over existing data — no new write path, no
counters. Honest about its proxies via ``notes`` (true event-level retrieval /
reinforcement frequency needs a counter, deferred to Stage 14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class MemoryHealth:
    user_id: UUID | None

    # lifecycle composition
    total_memories: int
    active_memories: int
    archived_memories: int
    promoted_memories: int
    promotion_rate: float          # promoted / total
    archive_rate: float            # archived / total

    # growth (memories created within the trailing window)
    created_last_7_days: int
    created_last_30_days: int

    # quality signals
    average_score: float
    avg_reinforcement_signal: float  # mean frequency-score over active (proxy)

    # knowledge-graph density
    graph_nodes: int
    graph_edges: int
    graph_density: float           # edges per node

    # rolling-summary coverage (scopes PROJECT / GOAL / EXPERIENCE)
    summary_scopes_expected: int   # scopes the user has active memories for
    summary_scopes_present: int    # of those, scopes with a current summary
    summary_coverage: float        # present / expected (1.0 when nothing expected)

    # contradiction / supersession + composition (Stage 16)
    contradiction_count: int = 0   # CONTRADICTS edges in the tenant's graph
    superseded_count: int = 0      # SUPERSEDES edges (resolved contradictions)
    type_distribution: dict[str, int] = field(default_factory=dict)  # by memory_type
    average_importance: float = 0.0
    average_confidence: float = 0.0

    # self-evolution composition (Stage 17)
    forgotten_count: int = 0       # memories in FORGOTTEN state
    episodic_count: int = 0
    semantic_count: int = 0
    cluster_count: int = 0         # distinct CLUSTER_MEMBER cluster ids
    promoted_from_count: int = 0   # PROMOTED_FROM edges (episodic->semantic)
    average_memory_age_days: float = 0.0
    retrieval_frequency_stats: dict[str, float] = field(default_factory=dict)  # total/avg/max
    importance_distribution: dict[str, int] = field(default_factory=dict)
    confidence_distribution: dict[str, int] = field(default_factory=dict)

    notes: dict[str, str] = field(default_factory=dict)

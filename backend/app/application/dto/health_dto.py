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

    notes: dict[str, str] = field(default_factory=dict)

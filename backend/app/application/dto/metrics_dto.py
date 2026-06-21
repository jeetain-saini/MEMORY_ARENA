"""Performance-metrics DTOs (Stage 14 Phase 5).

Framework-free snapshot of the in-memory metrics sink: counters (e.g. cache
hit/miss) and latency aggregates (e.g. retrieval / vector-search). Read by the
additive ``GET /observability/metrics`` endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LatencyStat:
    count: int
    avg_ms: float
    p50_ms: float
    p95_ms: float


@dataclass(frozen=True)
class MetricsSnapshot:
    counters: dict[str, int] = field(default_factory=dict)
    latencies: dict[str, LatencyStat] = field(default_factory=dict)

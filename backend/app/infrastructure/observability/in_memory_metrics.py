"""InMemoryMetricsSink — process-local counters + bounded latency samples.

Counters accumulate; each latency name keeps a bounded ring of recent samples
(default 1000) from which the snapshot computes avg/p50/p95 via nearest-rank.
Process-local and not durable — an observability aid (read via
``GET /observability/metrics``), not a metrics store. Shared process-wide via the
factory so writers and the endpoint reader see the same instance.
"""

from __future__ import annotations

from collections import deque

from app.application.dto.metrics_dto import LatencyStat, MetricsSnapshot
from app.application.interfaces.metrics_sink import MetricsSink


def _percentile(sorted_samples: list[float], pct: float) -> float:
    if not sorted_samples:
        return 0.0
    # Nearest-rank: rank = ceil(pct/100 * n), 1-indexed.
    rank = max(1, -(-int(pct) * len(sorted_samples) // 100))  # ceil division
    return sorted_samples[min(rank, len(sorted_samples)) - 1]


class InMemoryMetricsSink(MetricsSink):
    def __init__(self, *, sample_cap: int = 1000) -> None:
        self._counters: dict[str, int] = {}
        self._samples: dict[str, deque[float]] = {}
        self._cap = sample_cap

    def incr(self, name: str, amount: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + amount

    def observe(self, name: str, value_ms: float) -> None:
        bucket = self._samples.get(name)
        if bucket is None:
            bucket = deque(maxlen=self._cap)
            self._samples[name] = bucket
        bucket.append(float(value_ms))

    def snapshot(self) -> MetricsSnapshot:
        latencies: dict[str, LatencyStat] = {}
        for name, samples in self._samples.items():
            values = sorted(samples)
            count = len(values)
            latencies[name] = LatencyStat(
                count=count,
                avg_ms=round(sum(values) / count, 4) if count else 0.0,
                p50_ms=round(_percentile(values, 50), 4),
                p95_ms=round(_percentile(values, 95), 4),
            )
        return MetricsSnapshot(counters=dict(self._counters), latencies=latencies)

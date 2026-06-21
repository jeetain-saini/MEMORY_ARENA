"""NoOpMetricsSink — records nothing (the default).

Makes metric calls free so instrumentation on the hot path has no cost when
metrics are disabled.
"""

from __future__ import annotations

from app.application.dto.metrics_dto import MetricsSnapshot
from app.application.interfaces.metrics_sink import MetricsSink


class NoOpMetricsSink(MetricsSink):
    def incr(self, name: str, amount: int = 1) -> None:
        return None

    def observe(self, name: str, value_ms: float) -> None:
        return None

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot()

"""Metrics-sink factory — config-driven selection (Stage 14 Phase 5).

``NoOpMetricsSink`` (default) or ``InMemoryMetricsSink`` by ``METRICS_SINK``.
Cached as a process-wide singleton so counters accumulate across requests and the
metrics endpoint reads the same instance. ``build_metrics_sink.cache_clear()`` in
tests that change configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.metrics_sink import MetricsSink
from app.core.config import get_settings
from app.infrastructure.observability.in_memory_metrics import InMemoryMetricsSink
from app.infrastructure.observability.noop_metrics import NoOpMetricsSink


@lru_cache(maxsize=1)
def build_metrics_sink() -> MetricsSink:
    if get_settings().metrics_sink.lower() == "memory":
        return InMemoryMetricsSink()
    return NoOpMetricsSink()

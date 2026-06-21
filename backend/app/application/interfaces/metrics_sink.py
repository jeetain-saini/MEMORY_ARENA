"""MetricsSink port — lightweight in-process performance metrics.

Counters (``incr``) and latency observations (``observe``, milliseconds), plus a
``snapshot`` read for the metrics endpoint. Synchronous and allocation-light so
it is safe on the hot path; the NoOp default makes recording free. No external
observability dependency — this integrates with the Stage 13 in-process
observability surface only.

Metric *names* carry their dimension (e.g. ``cache.hit.analytics``); there is no
tag explosion to keep the snapshot trivially serializable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.metrics_dto import MetricsSnapshot


class MetricsSink(ABC):
    @abstractmethod
    def incr(self, name: str, amount: int = 1) -> None:
        """Increment a counter."""

    @abstractmethod
    def observe(self, name: str, value_ms: float) -> None:
        """Record a latency observation in milliseconds."""

    @abstractmethod
    def snapshot(self) -> MetricsSnapshot:
        """Return the current counters + latency aggregates."""

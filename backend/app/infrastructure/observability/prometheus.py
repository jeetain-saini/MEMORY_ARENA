"""Prometheus exposition (Phase 4 Observability).

Renders a :class:`MetricsSnapshot` (the in-process counters + latency aggregates
collected on the hot path) into Prometheus text exposition format, so an external
Prometheus can scrape MemoryArena without adding a metrics dependency to the hot
path. Counters become ``counter`` series; each latency name expands to avg / p50 /
p95 gauges plus a sample ``_count`` counter.

Metric names are sanitized to the Prometheus charset and namespaced under
``memoryarena_`` — e.g. the in-process counter ``cache.hit.analytics`` is exposed
as ``memoryarena_cache_hit_analytics``, and the latency ``retrieval`` becomes
``memoryarena_retrieval_latency_ms{quantile="0.95"}`` and
``memoryarena_retrieval_latency_count``.
"""

from __future__ import annotations

import re

from app.application.dto.metrics_dto import MetricsSnapshot

_PREFIX = "memoryarena_"
_INVALID = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize(name: str) -> str:
    safe = _INVALID.sub("_", name).strip("_")
    if safe and safe[0].isdigit():
        safe = f"_{safe}"
    return _PREFIX + safe


def render_prometheus(snapshot: MetricsSnapshot) -> str:
    """Return the snapshot as Prometheus text exposition (ends with a newline)."""
    lines: list[str] = []

    for raw_name, value in sorted(snapshot.counters.items()):
        metric = _sanitize(raw_name)
        lines.append(f"# TYPE {metric} counter")
        lines.append(f"{metric} {value}")

    for raw_name, stat in sorted(snapshot.latencies.items()):
        # The latency name already carries its unit (e.g. retrieval.latency_ms),
        # so expose it as-is with quantile labels plus a sample _count.
        metric = _sanitize(raw_name)
        lines.append(f"# TYPE {metric} gauge")
        lines.append(f'{metric}{{quantile="avg"}} {stat.avg_ms}')
        lines.append(f'{metric}{{quantile="0.5"}} {stat.p50_ms}')
        lines.append(f'{metric}{{quantile="0.95"}} {stat.p95_ms}')
        count_metric = metric + "_count"
        lines.append(f"# TYPE {count_metric} counter")
        lines.append(f"{count_metric} {stat.count}")

    return "\n".join(lines) + "\n"

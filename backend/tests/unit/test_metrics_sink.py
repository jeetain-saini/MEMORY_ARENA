"""Unit tests for the metrics sinks (in-memory + no-op) and factory."""

from __future__ import annotations

import os

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from app.infrastructure.observability.in_memory_metrics import InMemoryMetricsSink  # noqa: E402
from app.infrastructure.observability.noop_metrics import NoOpMetricsSink  # noqa: E402


def test_counters_accumulate() -> None:
    sink = InMemoryMetricsSink()
    sink.incr("cache.hit.analytics")
    sink.incr("cache.hit.analytics")
    sink.incr("cache.miss.analytics", 3)
    snap = sink.snapshot()
    assert snap.counters["cache.hit.analytics"] == 2
    assert snap.counters["cache.miss.analytics"] == 3


def test_latency_aggregates() -> None:
    sink = InMemoryMetricsSink()
    for v in (10.0, 20.0, 30.0, 40.0, 100.0):
        sink.observe("retrieval.latency_ms", v)
    stat = sink.snapshot().latencies["retrieval.latency_ms"]
    assert stat.count == 5
    assert stat.avg_ms == 40.0
    assert stat.p50_ms == 30.0   # nearest-rank: ceil(0.5*5)=3 -> 3rd value
    assert stat.p95_ms == 100.0  # ceil(0.95*5)=5 -> 5th value


def test_single_sample_percentiles() -> None:
    sink = InMemoryMetricsSink()
    sink.observe("vector_search.latency_ms", 7.5)
    stat = sink.snapshot().latencies["vector_search.latency_ms"]
    assert stat.count == 1
    assert stat.p50_ms == stat.p95_ms == stat.avg_ms == 7.5


def test_sample_cap_bounds_memory() -> None:
    sink = InMemoryMetricsSink(sample_cap=10)
    for i in range(100):
        sink.observe("x", float(i))
    assert sink.snapshot().latencies["x"].count == 10  # only the last 10 retained


def test_noop_records_nothing() -> None:
    sink = NoOpMetricsSink()
    sink.incr("a")
    sink.observe("b", 5.0)
    snap = sink.snapshot()
    assert snap.counters == {}
    assert snap.latencies == {}


def test_factory_default_is_noop() -> None:
    from app.core.config import get_settings
    from app.infrastructure.observability.metrics_factory import build_metrics_sink

    get_settings.cache_clear()
    build_metrics_sink.cache_clear()
    try:
        assert isinstance(build_metrics_sink(), NoOpMetricsSink)
    finally:
        get_settings.cache_clear()
        build_metrics_sink.cache_clear()


def test_factory_memory_selection() -> None:
    from app.core.config import get_settings
    from app.infrastructure.observability.metrics_factory import build_metrics_sink

    os.environ["METRICS_SINK"] = "memory"
    get_settings.cache_clear()
    build_metrics_sink.cache_clear()
    try:
        assert isinstance(build_metrics_sink(), InMemoryMetricsSink)
    finally:
        os.environ.pop("METRICS_SINK", None)
        get_settings.cache_clear()
        build_metrics_sink.cache_clear()

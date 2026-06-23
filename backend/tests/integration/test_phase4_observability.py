"""Phase 4 — Prometheus observability tests.

Proves the Prometheus exposition renderer and the /observability/prometheus
scrape endpoint expose every counter and latency aggregate (cache, intelligence/
maintenance, etc.) with sanitized, namespaced metric names.
"""

from __future__ import annotations

import os

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.dependencies.providers import get_metrics_sink  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.observability.in_memory_metrics import InMemoryMetricsSink  # noqa: E402
from app.infrastructure.observability.prometheus import render_prometheus  # noqa: E402
from app.main import create_app  # noqa: E402


# --- pure renderer ---------------------------------------------------------

def test_render_counters_and_latencies() -> None:
    sink = InMemoryMetricsSink()
    sink.incr("memories_promoted_total", 4)
    sink.incr("cache.hit.analytics", 2)
    sink.observe("retrieval.latency_ms", 10.0)
    sink.observe("retrieval.latency_ms", 20.0)

    text = render_prometheus(sink.snapshot())

    # Counters: sanitized + namespaced, with a TYPE line.
    assert "# TYPE memoryarena_memories_promoted_total counter" in text
    assert "memoryarena_memories_promoted_total 4" in text
    assert "memoryarena_cache_hit_analytics 2" in text  # dots -> underscores
    # Latency expands to avg/p50/p95 gauges + a count counter.
    assert 'memoryarena_retrieval_latency_ms{quantile="0.95"}' in text
    assert "memoryarena_retrieval_latency_ms_count 2" in text  # sample count series
    assert text.endswith("\n")


def test_render_is_deterministic_and_sorted() -> None:
    sink = InMemoryMetricsSink()
    sink.incr("b_metric", 1)
    sink.incr("a_metric", 1)
    text = render_prometheus(sink.snapshot())
    assert text.index("memoryarena_a_metric") < text.index("memoryarena_b_metric")


# --- scrape endpoint -------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    sink = InMemoryMetricsSink()
    sink.incr("cache.hit.analytics", 3)
    sink.incr("memories_forgotten_total", 5)
    sink.observe("vector.latency_ms", 8.0)
    app.dependency_overrides[get_metrics_sink] = lambda: sink
    return TestClient(app)


def test_prometheus_endpoint_exposes_text(client: TestClient) -> None:
    resp = client.get("/api/v1/observability/prometheus")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "memoryarena_cache_hit_analytics 3" in body
    assert "memoryarena_memories_forgotten_total 5" in body
    assert "memoryarena_vector_latency_ms" in body

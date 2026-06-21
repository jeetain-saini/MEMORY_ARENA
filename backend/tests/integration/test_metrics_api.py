"""API test for GET /observability/metrics (Stage 14 Phase 5)."""

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
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client_with_metrics() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    sink = InMemoryMetricsSink()
    sink.incr("cache.hit.analytics", 2)
    sink.incr("cache.miss.analytics", 1)
    sink.observe("retrieval.latency_ms", 12.0)
    app.dependency_overrides[get_metrics_sink] = lambda: sink
    return TestClient(app)


def test_metrics_endpoint_returns_snapshot(client_with_metrics: TestClient) -> None:
    resp = client_with_metrics.get("/api/v1/observability/metrics")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["counters"]["cache.hit.analytics"] == 2
    assert data["counters"]["cache.miss.analytics"] == 1
    assert data["latencies"]["retrieval.latency_ms"]["count"] == 1
    assert data["latencies"]["retrieval.latency_ms"]["p50_ms"] == 12.0


def test_metrics_endpoint_empty_by_default() -> None:
    # Default sink is NoOp -> empty snapshot.
    get_settings.cache_clear()
    app = create_app()
    resp = TestClient(app).get("/api/v1/observability/metrics")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"counters": {}, "latencies": {}}

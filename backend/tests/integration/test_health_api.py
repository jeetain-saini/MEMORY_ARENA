"""API test for GET /memories/health (Stage 13).

Exercises the real route + schema mapping with a fake-backed MemoryHealthService
(mirroring the query-API test pattern), so no DB or graph server is needed.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.dependencies.providers import get_memory_health_service  # noqa: E402
from app.application.services.observability.memory_health_service import (  # noqa: E402
    MemoryHealthService,
)
from app.core.config import get_settings  # noqa: E402
from app.domain.entities.memory import Memory  # noqa: E402
from app.domain.value_objects.memory_status import MemoryStatus  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository  # noqa: E402
from app.main import create_app  # noqa: E402

NOW = datetime.now(timezone.utc)
USER = uuid4()


class _FakeMemRepo:
    async def list_for_analytics(self, user_id=None):
        return [
            Memory(user_id=USER, content="a", memory_type=MemoryType.PROJECT),
            Memory(
                user_id=USER,
                content="b",
                memory_type=MemoryType.FACT,
                status=MemoryStatus.ARCHIVED,
                created_at=NOW - timedelta(days=40),
            ),
        ]


class _FakeSumRepo:
    async def list_for_user(self, user_id):
        return []


class _FakeUoW:
    memories = _FakeMemRepo()
    summaries = _FakeSumRepo()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


def _service() -> MemoryHealthService:
    return MemoryHealthService(_FakeUoW(), InMemoryGraphRepository())


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_memory_health_service] = _service
    return TestClient(app)


def test_health_endpoint_returns_metrics(client: TestClient) -> None:
    resp = client.get(f"/api/v1/memories/health?user_id={USER}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_memories"] == 2
    assert data["archived_memories"] == 1
    assert data["archive_rate"] == 0.5
    assert data["graph_nodes"] == 0
    assert data["graph_density"] == 0.0
    assert "retrieval_frequency" in data["notes"]


def test_health_endpoint_envelope(client: TestClient) -> None:
    resp = client.get(f"/api/v1/memories/health?user_id={USER}")
    body = resp.json()
    assert body["success"] is True
    assert "request_id" in body


def test_health_route_not_shadowed_by_memory_id(client: TestClient) -> None:
    # /memories/health must resolve to the health route, not /memories/{memory_id}.
    resp = client.get(f"/api/v1/memories/health?user_id={USER}")
    assert resp.status_code == 200
    assert "summary_coverage" in resp.json()["data"]


def test_health_global_scope_without_user(client: TestClient) -> None:
    resp = client.get("/api/v1/memories/health")
    assert resp.status_code == 200
    assert resp.json()["data"]["user_id"] is None

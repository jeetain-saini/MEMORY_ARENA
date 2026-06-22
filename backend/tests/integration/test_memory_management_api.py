"""API tests for Stage 16 endpoints: restore, contradiction resolution, graph
overview. The services are overridden with fakes, so these exercise the HTTP
layer (routing, schemas, envelopes) without a database or graph server.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.dependencies.providers import (  # noqa: E402
    get_contradiction_resolution_service,
    get_graph_repository,
    get_memory_intelligence_service,
)
from app.application.dto.graph_dto import GraphEdge, GraphEdgeType, GraphNode, NodeType  # noqa: E402
from app.application.dto.memory_dto import CreateMemoryResponse  # noqa: E402
from app.application.dto.resolution_dto import ContradictionResolutionResult  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain.value_objects.memory_status import MemoryStatus  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository  # noqa: E402
from app.main import create_app  # noqa: E402

USER = uuid4()


def _resp(status: MemoryStatus, content: str) -> CreateMemoryResponse:
    now = datetime.now(timezone.utc)
    return CreateMemoryResponse(
        id=uuid4(), user_id=USER, content=content, memory_type=MemoryType.FACT,
        status=status, total_score=0.5, version=1, is_promoted=False,
        created_at=now, updated_at=now,
    )


class _FakeIntelligence:
    async def restore_memory(self, memory_id, *, user_id=None):
        return _resp(MemoryStatus.ACTIVE, "restored")


class _FakeResolution:
    async def resolve(self, *, keep_id, archive_id, user_id=None):
        return ContradictionResolutionResult(
            kept=_resp(MemoryStatus.ACTIVE, "keep"),
            archived=_resp(MemoryStatus.ARCHIVED, "obsolete"),
            superseded_edge=True,
            contradiction_preserved=True,
        )


@pytest.fixture()
def client():
    get_settings.cache_clear()
    app = create_app()
    repo = InMemoryGraphRepository()
    app.dependency_overrides[get_memory_intelligence_service] = lambda: _FakeIntelligence()
    app.dependency_overrides[get_contradiction_resolution_service] = lambda: _FakeResolution()
    app.dependency_overrides[get_graph_repository] = lambda: repo
    with_client = TestClient(app)
    with_client._repo = repo  # type: ignore[attr-defined]
    yield with_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_restore_endpoint(client) -> None:
    r = client.post(f"/api/v1/memories/{uuid4()}/restore?user_id={USER}")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "active"


def test_resolve_contradiction_endpoint(client) -> None:
    r = client.post(
        "/api/v1/memories/contradictions/resolve",
        json={"user_id": str(USER), "keep_id": str(uuid4()), "archive_id": str(uuid4())},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["kept"]["status"] == "active"
    assert data["archived"]["status"] == "archived"
    assert data["superseded_edge"] is True
    assert data["contradiction_preserved"] is True


def test_graph_overview_endpoint(client) -> None:
    async def _seed():
        repo = client._repo
        a, b = str(uuid4()), str(uuid4())
        await repo.create_node(GraphNode(a, NodeType.FACT, "a", {"user_id": str(USER)}))
        await repo.create_node(GraphNode(b, NodeType.FACT, "b", {"user_id": str(USER)}))
        await repo.create_edge(GraphEdge(a, b, GraphEdgeType.SUPERSEDES))
        await repo.create_edge(GraphEdge(a, b, GraphEdgeType.CONTRADICTS))

    import asyncio

    asyncio.run(_seed())
    r = client.get(f"/api/v1/graph/overview/{USER}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["node_count"] == 2
    assert data["edge_count"] == 2
    edge_types = sorted(e["edge_type"] for e in data["edges"])
    assert edge_types == ["contradicts", "supersedes"]

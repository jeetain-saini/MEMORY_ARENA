"""API tests for the knowledge-graph endpoints (in-memory backend + fakes)."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.dependencies.providers import (  # noqa: E402
    get_graph_aware_retrieval_service,
    get_graph_repository,
    get_graph_traversal_service,
)
from app.application.dto.graph_dto import (  # noqa: E402
    ExpandedMemory,
    GraphAwareResult,
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    NodeType,
)
from app.application.services.graph.traversal_service import GraphTraversalService  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain.value_objects.memory_status import MemoryStatus  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository  # noqa: E402
from app.main import create_app  # noqa: E402

SEED = uuid4()
NEIGHBOR = uuid4()
USER = uuid4()


def _node(node_id, content) -> GraphNode:
    return GraphNode(
        node_id=str(node_id), node_type=NodeType.FACT, label=content,
        properties={
            "content": content, "memory_type": MemoryType.FACT.value,
            "status": MemoryStatus.ACTIVE.value, "user_id": str(USER),
        },
    )


def _build_repo() -> InMemoryGraphRepository:
    repo = InMemoryGraphRepository()

    async def populate() -> None:
        await repo.create_node(_node(SEED, "python seed"))
        await repo.create_node(_node(NEIGHBOR, "python neighbor"))
        await repo.create_edge(GraphEdge(str(SEED), str(NEIGHBOR), GraphEdgeType.RELATED_TO))

    asyncio.run(populate())
    return repo


class _FakeGraphAware:
    async def search(self, query, *, expand_depth=None) -> GraphAwareResult:
        return GraphAwareResult(
            query=query.query, user_id=query.user_id,
            results=[
                ExpandedMemory(
                    memory_id=SEED, content="python seed", memory_type=MemoryType.FACT,
                    status=MemoryStatus.ACTIVE, score=0.8, provenance="hybrid",
                ),
                ExpandedMemory(
                    memory_id=NEIGHBOR, content="python neighbor", memory_type=MemoryType.FACT,
                    status=MemoryStatus.ACTIVE, score=0.4, provenance="graph",
                    source_memory_id=SEED,
                ),
            ],
            hybrid_count=1, graph_count=1,
        )


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    repo = _build_repo()
    app.dependency_overrides[get_graph_repository] = lambda: repo
    app.dependency_overrides[get_graph_traversal_service] = lambda: GraphTraversalService(repo)
    app.dependency_overrides[get_graph_aware_retrieval_service] = lambda: _FakeGraphAware()
    return TestClient(app)


def test_search_returns_provenance_counts(client: TestClient) -> None:
    resp = client.post("/api/v1/graph/search", json={"query": "python", "user_id": str(USER)})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["hybrid_count"] == 1 and data["graph_count"] == 1
    provenances = {r["provenance"] for r in data["results"]}
    assert provenances == {"hybrid", "graph"}


def test_debug_returns_same_shape(client: TestClient) -> None:
    resp = client.post("/api/v1/graph/debug", json={"query": "python", "user_id": str(USER)})
    assert resp.status_code == 200
    assert resp.json()["data"]["graph_count"] == 1


def test_traverse_returns_subgraph(client: TestClient) -> None:
    resp = client.post("/api/v1/graph/traverse", json={"node_id": str(SEED), "depth": 1})
    assert resp.status_code == 200
    data = resp.json()["data"]
    ids = {n["node_id"] for n in data["nodes"]}
    assert {str(SEED), str(NEIGHBOR)} <= ids
    assert len(data["edges"]) == 1


def test_memory_view_returns_node_and_neighbors(client: TestClient) -> None:
    resp = client.get(f"/api/v1/graph/memory/{SEED}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["node"]["node_id"] == str(SEED)
    assert any(n["node_id"] == str(NEIGHBOR) for n in data["neighbors"])
    assert len(data["edges"]) == 1


def test_search_empty_query_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/graph/search", json={"query": "", "user_id": str(USER)})
    assert resp.status_code == 422

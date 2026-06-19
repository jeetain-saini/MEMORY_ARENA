"""API tests for the retrieval endpoints (fake service; no DB)."""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.dependencies.providers import get_memory_retrieval_service  # noqa: E402
from app.application.dto.retrieval_dto import (  # noqa: E402
    MemorySearchQuery,
    RetrievalResult,
    RetrievedMemory,
    ScoreBreakdown,
)
from app.core.config import get_settings  # noqa: E402
from app.domain.value_objects.memory_status import MemoryStatus  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.main import create_app  # noqa: E402


def _retrieved(user_id: UUID) -> RetrievedMemory:
    return RetrievedMemory(
        memory_id=uuid4(), user_id=user_id, content="paris", memory_type=MemoryType.FACT,
        status=MemoryStatus.ACTIVE, final_score=0.87,
        scores=ScoreBreakdown(
            vector_score=0.9, bm25_score=0.8, memory_score=0.5,
            recency_score=0.7, final_score=0.87,
        ),
    )


class FakeRetrievalService:
    async def search(self, query: MemorySearchQuery) -> RetrievalResult:
        return RetrievalResult(
            query=query.query, user_id=query.user_id, results=[_retrieved(query.user_id)], count=1
        )

    async def debug(self, query: MemorySearchQuery) -> RetrievalResult:
        return RetrievalResult(
            query=query.query, user_id=query.user_id, results=[_retrieved(query.user_id)], count=1
        )


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_memory_retrieval_service] = lambda: FakeRetrievalService()
    return TestClient(app)


def test_search_endpoint(client: TestClient) -> None:
    body = {"query": "paris", "user_id": str(uuid4()), "top_k": 5}
    resp = client.post("/api/v1/retrieval/search", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["count"] == 1
    assert data["data"]["results"][0]["content"] == "paris"


def test_debug_returns_score_breakdown(client: TestClient) -> None:
    body = {"query": "paris", "user_id": str(uuid4())}
    resp = client.post("/api/v1/retrieval/debug", json=body)
    assert resp.status_code == 200
    scores = resp.json()["data"]["results"][0]["scores"]
    for key in ("vector_score", "bm25_score", "memory_score", "recency_score", "final_score"):
        assert key in scores


def test_search_empty_query_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/retrieval/search", json={"query": "", "user_id": str(uuid4())})
    assert resp.status_code == 422


def test_search_filters_accepted(client: TestClient) -> None:
    body = {
        "query": "paris",
        "user_id": str(uuid4()),
        "filters": {"memory_types": ["fact"], "statuses": ["active"]},
    }
    resp = client.post("/api/v1/retrieval/search", json=body)
    assert resp.status_code == 200

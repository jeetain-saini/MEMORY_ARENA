"""API tests for the context-assembly endpoints (fake builder; no DB)."""

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

from app.api.v1.dependencies.providers import get_context_builder_service  # noqa: E402
from app.application.dto.context_dto import (  # noqa: E402
    CompressionStats,
    ConflictRecord,
    ContextDebugPackage,
    ContextMemory,
    ContextPackage,
    ContextRequest,
    DroppedMemory,
)
from app.core.config import get_settings  # noqa: E402
from app.domain.value_objects.memory_status import MemoryStatus  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.main import create_app  # noqa: E402


def _memory(content: str) -> ContextMemory:
    return ContextMemory(
        memory_id=uuid4(), content=content, memory_type=MemoryType.FACT,
        status=MemoryStatus.ACTIVE, score=0.8, tokens=5, is_promoted=False,
    )


def _package(request: ContextRequest) -> ContextPackage:
    mem = _memory("python is great")
    return ContextPackage(
        query=request.query, user_id=request.user_id, memories=[mem],
        context_text="- (fact) python is great", total_tokens=5,
        max_tokens=request.max_tokens, metadata=request.metadata,
    )


class FakeContextBuilder:
    async def build(self, request: ContextRequest) -> ContextPackage:
        return _package(request)

    async def debug(self, request: ContextRequest) -> ContextDebugPackage:
        package = _package(request)
        return ContextDebugPackage(
            package=package,
            selected=package.memories,
            dropped=[DroppedMemory(memory_id=uuid4(), content="dup", reason="duplicate")],
            conflicts=[ConflictRecord(
                memory_id_a=uuid4(), memory_id_b=uuid4(), reason="negation_contradiction",
                content_a="I use Python", content_b="I no longer use Python",
            )],
            consolidations=[],
            compression=CompressionStats(original_tokens=10, compressed_tokens=5, ratio=0.5, removed_memories=1),
        )


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_context_builder_service] = lambda: FakeContextBuilder()
    return TestClient(app)


def test_build_endpoint(client: TestClient) -> None:
    body = {"query": "python", "user_id": str(uuid4()), "max_tokens": 1000}
    resp = client.post("/api/v1/context/build", json=body)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_tokens"] == 5
    assert data["context_text"].startswith("- (fact)")
    assert len(data["memories"]) == 1


def test_debug_endpoint_returns_provenance(client: TestClient) -> None:
    body = {"query": "python", "user_id": str(uuid4())}
    resp = client.post("/api/v1/context/debug", json=body)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "selected" in data and "dropped" in data
    assert data["conflicts"][0]["reason"] == "negation_contradiction"
    assert data["compression"]["ratio"] == 0.5
    assert data["dropped"][0]["reason"] == "duplicate"


def test_build_empty_query_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/context/build", json={"query": "", "user_id": str(uuid4())})
    assert resp.status_code == 422


def test_build_accepts_filters_and_metadata(client: TestClient) -> None:
    body = {
        "query": "python", "user_id": str(uuid4()),
        "filters": {"statuses": ["active"]}, "metadata": {"session": "abc"},
    }
    resp = client.post("/api/v1/context/build", json=body)
    assert resp.status_code == 200


def test_build_invalid_max_tokens_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/context/build", json={"query": "x", "user_id": str(uuid4()), "max_tokens": 0})
    assert resp.status_code == 422

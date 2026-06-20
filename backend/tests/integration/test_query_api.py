"""API tests for the query-time agent endpoints (fake-backed runtime; no DB).

Exercises the real route + schema mapping + SequentialAgentRuntime, with the
three wrapped services replaced by offline fakes. Covers ``/query`` and the
``/query/stream`` SSE endpoint.
"""

from __future__ import annotations

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

from app.api.v1.dependencies.providers import get_query_use_case  # noqa: E402
from app.application.services.agent.tools import (  # noqa: E402
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)
from app.application.services.agent.toolset import AgentToolSet  # noqa: E402
from app.application.services.context.tokenization import HeuristicTokenCounter  # noqa: E402
from app.application.use_cases.query_memory_use_cases_impl import (  # noqa: E402
    QueryMemoryUseCaseImpl,
)
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.llm.graphs.sequential_agent_runtime import (  # noqa: E402
    SequentialAgentRuntime,
)
from app.main import create_app  # noqa: E402
from tests.unit._agent_fakes import (  # noqa: E402
    FakeContextBuilder,
    FakeGraphAwareService,
    FakeLLMProvider,
    FakeRetrievalService,
    make_retrieved,
)


def _use_case() -> QueryMemoryUseCaseImpl:
    uid = uuid4()
    toolset = AgentToolSet(
        MemorySearchTool(FakeRetrievalService([make_retrieved("I use Python", uid)])),
        GraphExpansionTool(FakeGraphAwareService(neighbors=[("Python is typed", uuid4())])),
        ContextBuilderTool(FakeContextBuilder()),
    )
    runtime = SequentialAgentRuntime(toolset, FakeLLMProvider("python is a language"), HeuristicTokenCounter())
    return QueryMemoryUseCaseImpl(runtime)


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_query_use_case] = _use_case
    return TestClient(app)


def test_query_returns_answer_and_citations(client: TestClient) -> None:
    resp = client.post("/api/v1/query", json={"user_id": str(uuid4()), "query": "python"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answer"] == "python is a language"
    assert data["finish_reason"] == "completed"
    assert len(data["citations"]) >= 1


def test_query_citation_shape(client: TestClient) -> None:
    resp = client.post("/api/v1/query", json={"user_id": str(uuid4()), "query": "python"})
    citation = resp.json()["data"]["citations"][0]
    assert set(citation) == {"memory_id", "content", "memory_type", "provenance", "score"}
    assert citation["provenance"] in ("hybrid", "graph")


def test_query_empty_query_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/query", json={"user_id": str(uuid4()), "query": ""})
    assert resp.status_code == 422


def test_query_missing_user_id_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/query", json={"query": "python"})
    assert resp.status_code == 422


def test_query_envelope_has_request_id(client: TestClient) -> None:
    resp = client.post("/api/v1/query", json={"user_id": str(uuid4()), "query": "python"})
    body = resp.json()
    assert body["success"] is True
    assert "request_id" in body


def test_query_stream_is_event_stream(client: TestClient) -> None:
    resp = client.post("/api/v1/query/stream", json={"user_id": str(uuid4()), "query": "python"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")


def test_query_stream_emits_step_and_done(client: TestClient) -> None:
    resp = client.post("/api/v1/query/stream", json={"user_id": str(uuid4()), "query": "python"})
    body = resp.text
    assert "event: step" in body
    assert "event: answer" in body
    assert "event: done" in body
    assert "completed" in body

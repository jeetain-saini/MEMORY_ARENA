"""API tests for GET /observability/traces and trace recording (Stage 13).

End-to-end with offline fakes: a shared InMemoryTraceRecorder is wired into both
the query use case (writes on /query) and the traces endpoint (reads), proving a
query run is recorded and surfaced. No DB, graph server, or network.
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

from app.api.v1.dependencies.providers import (  # noqa: E402
    get_query_use_case,
    get_trace_recorder,
)
from app.application.services.agent.tools import (  # noqa: E402
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)
from app.application.services.agent.toolset import AgentToolSet  # noqa: E402
from app.application.services.context.tokenization import HeuristicTokenCounter  # noqa: E402
from app.application.services.observability.frozen_clock import FrozenClock  # noqa: E402
from app.application.use_cases.query_memory_use_cases_impl import (  # noqa: E402
    QueryMemoryUseCaseImpl,
)
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.llm.graphs.sequential_agent_runtime import (  # noqa: E402
    SequentialAgentRuntime,
)
from app.infrastructure.observability.in_memory_recorder import InMemoryTraceRecorder  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.unit._agent_fakes import (  # noqa: E402
    FakeContextBuilder,
    FakeGraphAwareService,
    FakeLLMProvider,
    FakeRetrievalService,
    make_retrieved,
)

_RECORDER = InMemoryTraceRecorder()


def _use_case() -> QueryMemoryUseCaseImpl:
    uid = uuid4()
    toolset = AgentToolSet(
        MemorySearchTool(FakeRetrievalService([make_retrieved("I use Python", uid)])),
        GraphExpansionTool(FakeGraphAwareService(neighbors=[("Python is typed", uuid4())])),
        ContextBuilderTool(FakeContextBuilder()),
    )
    runtime = SequentialAgentRuntime(
        toolset,
        FakeLLMProvider("python is a language"),
        HeuristicTokenCounter(),
        clock=FrozenClock(auto_advance=0.01),
    )
    return QueryMemoryUseCaseImpl(runtime, _RECORDER)


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    _RECORDER._buffer.clear()  # isolate each test
    app = create_app()
    app.dependency_overrides[get_query_use_case] = _use_case
    app.dependency_overrides[get_trace_recorder] = lambda: _RECORDER
    return TestClient(app)


def test_traces_empty_initially(client: TestClient) -> None:
    resp = client.get("/api/v1/observability/traces")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_query_run_is_recorded_and_listed(client: TestClient) -> None:
    uid = str(uuid4())
    client.post("/api/v1/query", json={"user_id": uid, "query": "python"})
    resp = client.get("/api/v1/observability/traces")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["finish_reason"] == "completed"
    assert data[0]["total_duration_ms"] == 40.0
    assert data[0]["retrieval"]["candidate_count"] == 1


def test_traces_filter_by_user(client: TestClient) -> None:
    a, b = str(uuid4()), str(uuid4())
    client.post("/api/v1/query", json={"user_id": a, "query": "python"})
    client.post("/api/v1/query", json={"user_id": b, "query": "python"})
    resp = client.get(f"/api/v1/observability/traces?user_id={a}")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["user_id"] == a


def test_traces_envelope(client: TestClient) -> None:
    resp = client.get("/api/v1/observability/traces")
    body = resp.json()
    assert body["success"] is True
    assert "request_id" in body

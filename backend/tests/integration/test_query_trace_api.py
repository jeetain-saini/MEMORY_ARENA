"""API test: the /query response surfaces the Stage 13 observability trace.

Additive, backward-compatible: the existing answer/citations/finish_reason
fields are unchanged; a new optional ``trace`` object is included. A
``FrozenClock`` makes the stage durations deterministic end-to-end.
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
from app.application.services.observability.frozen_clock import FrozenClock  # noqa: E402
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
    runtime = SequentialAgentRuntime(
        toolset,
        FakeLLMProvider("python is a language"),
        HeuristicTokenCounter(),
        clock=FrozenClock(auto_advance=0.01),
    )
    return QueryMemoryUseCaseImpl(runtime)


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_query_use_case] = _use_case
    return TestClient(app)


def test_query_response_includes_trace(client: TestClient) -> None:
    resp = client.post("/api/v1/query", json={"user_id": str(uuid4()), "query": "python"})
    assert resp.status_code == 200
    trace = resp.json()["data"]["trace"]
    assert trace is not None
    assert trace["finish_reason"] == "completed"
    assert [t["step"] for t in trace["timings"]] == [
        "retrieve",
        "expand",
        "build_context",
        "generate",
    ]
    assert trace["total_duration_ms"] == 40.0


def test_query_trace_sections_present(client: TestClient) -> None:
    resp = client.post("/api/v1/query", json={"user_id": str(uuid4()), "query": "python"})
    trace = resp.json()["data"]["trace"]
    assert trace["retrieval"]["candidate_count"] == 1
    assert trace["graph"]["graph_count"] == 1
    assert trace["context"]["memory_count"] == 2
    assert 0.0 <= trace["context"]["budget_utilization"] <= 1.0


def test_query_stream_step_frames_carry_duration(client: TestClient) -> None:
    resp = client.post("/api/v1/query/stream", json={"user_id": str(uuid4()), "query": "python"})
    assert "duration_ms" in resp.text

"""Unit tests for the LangSmith trace recorder (Stage 13).

The recorder's *behavior* is tested with an injected fake client, so it needs no
``langsmith`` install (the package is only imported when constructing a real
client). The factory's LangSmith *selection* path does import the package, so
that test is skip-guarded — mirroring the lazy ``langgraph`` suites.
"""

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

from app.application.dto.observability_dto import RequestTrace, StepTiming  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.observability.factory import build_trace_recorder  # noqa: E402
from app.infrastructure.observability.langsmith_recorder import LangSmithTraceRecorder  # noqa: E402


class _FakeClient:
    def __init__(self, *, raises: bool = False) -> None:
        self.runs: list[dict] = []
        self._raises = raises

    def create_run(self, **kwargs) -> None:
        if self._raises:
            raise RuntimeError("langsmith down")
        self.runs.append(kwargs)


def _trace() -> RequestTrace:
    return RequestTrace(
        query="hello",
        user_id=uuid4(),
        finish_reason="completed",
        total_duration_ms=40.0,
        timings=[StepTiming(step="retrieve", duration_ms=10.0)],
        tool_calls=3,
        total_tokens=120,
    )


def test_records_via_injected_client_without_langsmith_installed() -> None:
    client = _FakeClient()
    recorder = LangSmithTraceRecorder(client=client, project="test-proj")
    asyncio.run(recorder.record(_trace()))
    assert len(client.runs) == 1
    run = client.runs[0]
    assert run["project_name"] == "test-proj"
    assert run["inputs"]["query"] == "hello"
    assert run["outputs"]["finish_reason"] == "completed"


def test_record_swallows_client_errors() -> None:
    recorder = LangSmithTraceRecorder(client=_FakeClient(raises=True))
    # Must not raise — observability can never break a request.
    asyncio.run(recorder.record(_trace()))


def test_recent_returns_empty() -> None:
    recorder = LangSmithTraceRecorder(client=_FakeClient())
    assert asyncio.run(recorder.recent()) == []


def test_factory_selects_langsmith_when_enabled() -> None:
    pytest.importorskip("langsmith")
    os.environ["LANGSMITH_ENABLED"] = "true"
    get_settings.cache_clear()
    build_trace_recorder.cache_clear()
    try:
        assert isinstance(build_trace_recorder(), LangSmithTraceRecorder)
    finally:
        os.environ.pop("LANGSMITH_ENABLED", None)
        get_settings.cache_clear()
        build_trace_recorder.cache_clear()

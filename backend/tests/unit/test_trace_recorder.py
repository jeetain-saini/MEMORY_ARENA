"""Unit tests for the TraceRecorder adapters and factory (Stage 13)."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from app.application.dto.observability_dto import RequestTrace  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.observability.factory import build_trace_recorder  # noqa: E402
from app.infrastructure.observability.in_memory_recorder import InMemoryTraceRecorder  # noqa: E402
from app.infrastructure.observability.noop_recorder import NoOpTraceRecorder  # noqa: E402


def _trace(user_id, query: str = "q") -> RequestTrace:
    return RequestTrace(
        query=query, user_id=user_id, finish_reason="completed", total_duration_ms=1.0
    )


def _run(coro):
    return asyncio.run(coro)


# --- NoOp ------------------------------------------------------------------

def test_noop_records_nothing() -> None:
    rec = NoOpTraceRecorder()
    _run(rec.record(_trace(uuid4())))
    assert _run(rec.recent()) == []


# --- InMemory --------------------------------------------------------------

def test_in_memory_records_and_returns_newest_first() -> None:
    rec = InMemoryTraceRecorder()
    uid = uuid4()
    _run(rec.record(_trace(uid, "first")))
    _run(rec.record(_trace(uid, "second")))
    recent = _run(rec.recent())
    assert [t.query for t in recent] == ["second", "first"]


def test_in_memory_capacity_evicts_oldest() -> None:
    rec = InMemoryTraceRecorder(capacity=2)
    uid = uuid4()
    for q in ("a", "b", "c"):
        _run(rec.record(_trace(uid, q)))
    assert [t.query for t in _run(rec.recent())] == ["c", "b"]


def test_in_memory_limit() -> None:
    rec = InMemoryTraceRecorder()
    uid = uuid4()
    for i in range(5):
        _run(rec.record(_trace(uid, str(i))))
    assert len(_run(rec.recent(limit=2))) == 2


def test_in_memory_filters_by_user() -> None:
    rec = InMemoryTraceRecorder()
    a, b = uuid4(), uuid4()
    _run(rec.record(_trace(a, "a1")))
    _run(rec.record(_trace(b, "b1")))
    _run(rec.record(_trace(a, "a2")))
    recent = _run(rec.recent(user_id=a))
    assert [t.query for t in recent] == ["a2", "a1"]


# --- factory ---------------------------------------------------------------

def _reset_caches() -> None:
    get_settings.cache_clear()
    build_trace_recorder.cache_clear()


def test_factory_defaults_to_in_memory() -> None:
    os.environ.pop("TRACE_RECORDER", None)
    os.environ.pop("LANGSMITH_ENABLED", None)
    _reset_caches()
    try:
        assert isinstance(build_trace_recorder(), InMemoryTraceRecorder)
    finally:
        _reset_caches()


def test_factory_selects_noop() -> None:
    os.environ["TRACE_RECORDER"] = "noop"
    _reset_caches()
    try:
        assert isinstance(build_trace_recorder(), NoOpTraceRecorder)
    finally:
        os.environ.pop("TRACE_RECORDER", None)
        _reset_caches()


def test_factory_singleton_is_shared() -> None:
    _reset_caches()
    try:
        assert build_trace_recorder() is build_trace_recorder()
    finally:
        _reset_caches()

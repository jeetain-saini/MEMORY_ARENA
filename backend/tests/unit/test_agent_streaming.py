"""Unit tests for SequentialAgentRuntime.stream (SSE event sequence)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.agent_dto import AgentConfig, AgentRequest
from app.application.services.agent.tools import (
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)
from app.application.services.agent.toolset import AgentToolSet
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.infrastructure.llm.graphs.sequential_agent_runtime import SequentialAgentRuntime
from tests.unit._agent_fakes import (
    FakeContextBuilder,
    FakeGraphAwareService,
    FakeLLMProvider,
    FakeRetrievalService,
    make_retrieved,
)

_COUNTER = HeuristicTokenCounter()


def _runtime(*, provider=None, builder=None, uid=None):
    uid = uid or uuid4()
    toolset = AgentToolSet(
        MemorySearchTool(FakeRetrievalService([make_retrieved("I use Python", uid)])),
        GraphExpansionTool(FakeGraphAwareService(neighbors=[("typed lang", uuid4())])),
        ContextBuilderTool(builder or FakeContextBuilder()),
    )
    return SequentialAgentRuntime(toolset, provider or FakeLLMProvider("answer"), _COUNTER), uid


def _collect(runtime, request) -> list:
    async def go() -> list:
        return [ev async for ev in runtime.stream(request)]

    return asyncio.run(go())


def _req(uid, **cfg) -> AgentRequest:
    return AgentRequest(user_id=uid, query="python", config=AgentConfig(**cfg))


def test_stream_emits_step_answer_citations_done() -> None:
    runtime, uid = _runtime()
    events = _collect(runtime, _req(uid))
    kinds = [e.event for e in events]
    assert kinds.count("step") == 4              # retrieve, expand, build, generate
    assert "answer" in kinds
    assert "citations" in kinds
    assert kinds[-1] == "done"


def test_stream_done_carries_finish_reason() -> None:
    runtime, uid = _runtime()
    events = _collect(runtime, _req(uid))
    done = events[-1]
    assert done.event == "done"
    assert done.data["finish_reason"] == "completed"


def test_stream_answer_event_has_answer() -> None:
    runtime, uid = _runtime()
    events = _collect(runtime, _req(uid))
    answer_ev = next(e for e in events if e.event == "answer")
    assert answer_ev.data["answer"]


def test_stream_emits_error_on_context_failure() -> None:
    runtime, uid = _runtime(builder=FakeContextBuilder(raises=True))
    events = _collect(runtime, _req(uid))
    kinds = [e.event for e in events]
    assert "error" in kinds
    assert kinds[-1] == "done"
    assert events[-1].data["finish_reason"] == "error"


def test_stream_timeout_emits_error_then_done() -> None:
    runtime, uid = _runtime(provider=FakeLLMProvider("late", sleep=0.2))
    events = _collect(runtime, _req(uid, timeout_seconds=0.05))
    kinds = [e.event for e in events]
    assert "error" in kinds
    assert kinds[-1] == "done"
    assert events[-1].data["finish_reason"] == "timeout"


def test_stream_always_terminates_with_done() -> None:
    runtime, uid = _runtime()
    events = _collect(runtime, _req(uid, max_iterations=0))
    assert events[-1].event == "done"
    assert events[-1].data["finish_reason"] == "max_iterations"

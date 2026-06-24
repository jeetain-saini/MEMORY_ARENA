"""Unit tests for SequentialAgentRuntime: flow, guards, recovery, citations."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.agent_dto import (
    FINISH_COMPLETED,
    FINISH_ERROR,
    FINISH_MAX_ITERATIONS,
    FINISH_MAX_TOOL_CALLS,
    FINISH_TIMEOUT,
    AgentConfig,
    AgentRequest,
)
from app.application.services.agent.tools import (
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)
from app.application.services.agent.toolset import AgentToolSet
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.infrastructure.llm.graphs.sequential_agent_runtime import SequentialAgentRuntime
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider
from tests.unit._agent_fakes import (
    FakeContextBuilder,
    FakeGraphAwareService,
    FakeLLMProvider,
    FakeRetrievalService,
    make_retrieved,
)

_COUNTER = HeuristicTokenCounter()


def _runtime(
    *,
    retrieval=None,
    graph=None,
    builder=None,
    provider=None,
    uid=None,
):
    uid = uid or uuid4()
    retrieval = retrieval or FakeRetrievalService([make_retrieved("I use Python", uid)])
    graph = graph or FakeGraphAwareService(neighbors=[("Python is typed", uuid4())])
    builder = builder or FakeContextBuilder()
    provider = provider or FakeLLMProvider("the answer about python")
    toolset = AgentToolSet(
        MemorySearchTool(retrieval), GraphExpansionTool(graph), ContextBuilderTool(builder)
    )
    return SequentialAgentRuntime(toolset, provider, _COUNTER), uid


def _request(uid, **cfg) -> AgentRequest:
    return AgentRequest(user_id=uid, query="python", config=AgentConfig(**cfg))


# --- happy path ------------------------------------------------------------

def test_respond_completes_all_stages() -> None:
    runtime, uid = _runtime()
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert resp.finish_reason == FINISH_COMPLETED
    assert resp.answer
    steps = [s.step for s in resp.trace.steps]
    assert steps == ["retrieve", "expand", "build_context", "generate"]


def test_context_package_is_primary_input_to_generation() -> None:
    # DeterministicLLMProvider echoes its prompt, so the answer must contain the
    # context's content — proving generation consumed the ContextPackage.
    runtime, uid = _runtime(provider=DeterministicLLMProvider())
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert "python" in resp.answer.lower()


def test_graph_expansion_is_consumed() -> None:
    runtime, uid = _runtime()
    resp = asyncio.run(runtime.respond(_request(uid)))
    provenances = {c.provenance for c in resp.citations}
    assert "hybrid" in provenances
    assert "graph" in provenances


def test_single_retrieval_no_double_call() -> None:
    uid = uuid4()
    builder = FakeContextBuilder()
    runtime, _ = _runtime(uid=uid, builder=builder)
    asyncio.run(runtime.respond(_request(uid)))
    # The builder consumed the agent's combined candidate set (pre-retrieved),
    # i.e. it did not run its own retrieval.
    assert builder.last_retrieved is not None
    assert len(builder.last_retrieved) == 2  # base hit + graph neighbor


# --- guards ----------------------------------------------------------------

def test_max_iterations_guard() -> None:
    runtime, uid = _runtime()
    resp = asyncio.run(runtime.respond(_request(uid, max_iterations=0)))
    assert resp.finish_reason == FINISH_MAX_ITERATIONS
    assert resp.answer == ""


def test_max_tool_calls_guard() -> None:
    runtime, uid = _runtime()
    resp = asyncio.run(runtime.respond(_request(uid, max_tool_calls=1)))
    assert resp.finish_reason == FINISH_MAX_TOOL_CALLS
    assert resp.trace.tool_calls == 1


def test_token_guard_truncates_answer() -> None:
    # Echoing provider returns a large answer; the cap truncates it.
    runtime, uid = _runtime(provider=DeterministicLLMProvider())
    resp = asyncio.run(runtime.respond(_request(uid, answer_max_tokens=5)))
    assert _COUNTER.count(resp.answer) <= 5


def test_timeout_guard() -> None:
    slow = FakeLLMProvider("late", sleep=0.2)
    runtime, uid = _runtime(provider=slow)
    resp = asyncio.run(runtime.respond(_request(uid, timeout_seconds=0.05)))
    assert resp.finish_reason == FINISH_TIMEOUT


def test_max_citations_cap() -> None:
    uid = uuid4()
    retrieval = FakeRetrievalService([make_retrieved(f"mem {i}", uid, score=i / 10) for i in range(6)])
    runtime, _ = _runtime(uid=uid, retrieval=retrieval, graph=FakeGraphAwareService())
    resp = asyncio.run(runtime.respond(_request(uid, max_citations=2)))
    assert len(resp.citations) <= 2


# --- tool-failure recovery -------------------------------------------------

def test_retrieval_failure_degrades_gracefully() -> None:
    runtime, uid = _runtime(retrieval=FakeRetrievalService(raises=True), graph=FakeGraphAwareService())
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert resp.finish_reason == FINISH_COMPLETED  # degraded, not failed
    retrieve_step = next(s for s in resp.trace.steps if s.step == "retrieve")
    assert not retrieve_step.ok


def test_graph_failure_degrades_gracefully() -> None:
    uid = uuid4()
    runtime, _ = _runtime(uid=uid, graph=FakeGraphAwareService(raises=True))
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert resp.finish_reason == FINISH_COMPLETED
    expand_step = next(s for s in resp.trace.steps if s.step == "expand")
    assert not expand_step.ok
    assert resp.answer  # still answered from base retrieval


def test_context_failure_is_terminal_error() -> None:
    runtime, uid = _runtime(builder=FakeContextBuilder(raises=True))
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert resp.finish_reason == FINISH_ERROR
    assert resp.answer == ""


def test_generation_failure_falls_back_gracefully() -> None:
    # A failing LLM no longer kills the response: the agent retries, then falls
    # back to a deterministic answer from retrieved context — never empty/error.
    runtime, uid = _runtime(provider=FakeLLMProvider(raises=True))
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert resp.finish_reason == FINISH_COMPLETED
    assert resp.answer.strip() != ""

"""Unit tests for Stage 13 agent observability: stage timing + RequestTrace.

Uses the offline agent fakes and a deterministic ``FrozenClock`` so per-stage
durations are exact (each stage reads the clock once at start and once at end,
so with ``auto_advance=0.01`` every measured stage is precisely 10ms).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.agent_dto import FINISH_COMPLETED, FINISH_ERROR, AgentConfig, AgentRequest
from app.application.services.agent.tools import (
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)
from app.application.services.agent.toolset import AgentToolSet
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.application.services.observability.frozen_clock import FrozenClock
from app.infrastructure.llm.graphs.sequential_agent_runtime import SequentialAgentRuntime
from tests.unit._agent_fakes import (
    FakeContextBuilder,
    FakeGraphAwareService,
    FakeLLMProvider,
    FakeRetrievalService,
    make_retrieved,
)

_COUNTER = HeuristicTokenCounter()


def _runtime(*, builder=None, provider=None, graph=None, clock=None, uid=None):
    uid = uid or uuid4()
    retrieval = FakeRetrievalService([make_retrieved("I use Python", uid)])
    graph = graph or FakeGraphAwareService(neighbors=[("Python is typed", uuid4())])
    builder = builder or FakeContextBuilder()
    provider = provider or FakeLLMProvider("python is a language")
    toolset = AgentToolSet(
        MemorySearchTool(retrieval), GraphExpansionTool(graph), ContextBuilderTool(builder)
    )
    return SequentialAgentRuntime(toolset, provider, _COUNTER, clock=clock), uid


def _request(uid, **cfg) -> AgentRequest:
    return AgentRequest(user_id=uid, query="python", config=AgentConfig(**cfg))


# --- stage timing ----------------------------------------------------------

def test_each_stage_records_deterministic_duration() -> None:
    runtime, uid = _runtime(clock=FrozenClock(auto_advance=0.01))
    resp = asyncio.run(runtime.respond(_request(uid)))
    durations = {s.step: s.duration_ms for s in resp.trace.steps}
    assert durations == {
        "retrieve": 10.0,
        "expand": 10.0,
        "build_context": 10.0,
        "generate": 10.0,
    }


def test_trace_total_duration_is_sum_of_steps() -> None:
    runtime, uid = _runtime(clock=FrozenClock(auto_advance=0.01))
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert resp.trace.total_duration_ms == 40.0


def test_timing_skipped_when_no_clock_injected_defaults_to_real_clock() -> None:
    # No injected clock -> MonotonicClock default -> durations are real (>= 0).
    runtime, uid = _runtime(clock=None)
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert all(s.duration_ms >= 0.0 for s in resp.trace.steps)


# --- request trace assembly ------------------------------------------------

def test_request_trace_is_assembled() -> None:
    runtime, uid = _runtime(clock=FrozenClock(auto_advance=0.01))
    resp = asyncio.run(runtime.respond(_request(uid)))
    trace = resp.request_trace
    assert trace is not None
    assert trace.finish_reason == FINISH_COMPLETED
    assert [t.step for t in trace.timings] == ["retrieve", "expand", "build_context", "generate"]
    assert trace.total_duration_ms == 40.0


def test_request_trace_retrieval_section() -> None:
    runtime, uid = _runtime(clock=FrozenClock(auto_advance=0.01))
    resp = asyncio.run(runtime.respond(_request(uid)))
    r = resp.request_trace.retrieval
    assert r is not None
    assert r.candidate_count == 1
    assert r.returned_count == 1
    assert r.top_scores == [0.9]
    assert r.duration_ms == 10.0


def test_request_trace_graph_section() -> None:
    runtime, uid = _runtime(clock=FrozenClock(auto_advance=0.01))
    resp = asyncio.run(runtime.respond(_request(uid)))
    g = resp.request_trace.graph
    assert g is not None
    assert g.enabled is True
    assert g.hybrid_count == 1
    assert g.graph_count == 1
    assert g.influence_scores == [0.4]


def test_request_trace_context_section_reports_budget_utilization() -> None:
    runtime, uid = _runtime(clock=FrozenClock(auto_advance=0.01))
    resp = asyncio.run(runtime.respond(_request(uid, max_tokens=1000)))
    c = resp.request_trace.context
    assert c is not None
    assert c.memory_count == 2  # base hit + graph neighbor
    assert c.max_tokens == 1000
    assert 0.0 < c.budget_utilization < 1.0
    assert round(c.budget_utilization, 6) == round(c.total_tokens / 1000, 6)


def test_request_trace_graph_disabled_when_expansion_off() -> None:
    runtime, uid = _runtime(clock=FrozenClock(auto_advance=0.01))
    resp = asyncio.run(runtime.respond(_request(uid, expand_graph=False)))
    # Expansion never ran, so there is no graph section, and context still built.
    assert resp.request_trace.graph is None
    assert resp.request_trace.context is not None


def test_request_trace_on_terminal_error_has_no_context() -> None:
    runtime, uid = _runtime(builder=FakeContextBuilder(raises=True), clock=FrozenClock(auto_advance=0.01))
    resp = asyncio.run(runtime.respond(_request(uid)))
    assert resp.finish_reason == FINISH_ERROR
    assert resp.request_trace.finish_reason == FINISH_ERROR
    assert resp.request_trace.context is None

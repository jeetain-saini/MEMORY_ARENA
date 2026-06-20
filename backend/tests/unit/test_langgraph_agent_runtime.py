"""LangGraphAgentRuntime parity + guards (skip-guarded on langgraph).

The whole module skips when ``langgraph`` is not installed, mirroring the
LangGraph extraction/consolidation suites. Offline default is the sequential
runtime; this asserts the graph runtime produces equivalent results and honors
the guardrails.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

pytest.importorskip("langgraph")

from app.application.dto.agent_dto import (  # noqa: E402
    FINISH_MAX_ITERATIONS,
    AgentConfig,
    AgentRequest,
)
from app.application.services.agent.tools import (  # noqa: E402
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)
from app.application.services.agent.toolset import AgentToolSet  # noqa: E402
from app.application.services.context.tokenization import HeuristicTokenCounter  # noqa: E402
from app.infrastructure.llm.graphs.agent_graph import LangGraphAgentRuntime  # noqa: E402
from app.infrastructure.llm.graphs.sequential_agent_runtime import (  # noqa: E402
    SequentialAgentRuntime,
)
from tests.unit._agent_fakes import (  # noqa: E402
    FakeContextBuilder,
    FakeGraphAwareService,
    FakeLLMProvider,
    FakeRetrievalService,
    make_retrieved,
)

_COUNTER = HeuristicTokenCounter()


def _toolset(uid):
    return AgentToolSet(
        MemorySearchTool(FakeRetrievalService([make_retrieved("I use Python", uid)])),
        GraphExpansionTool(FakeGraphAwareService(neighbors=[("typed lang", uuid4())])),
        ContextBuilderTool(FakeContextBuilder()),
    )


def _req(uid, **cfg) -> AgentRequest:
    return AgentRequest(user_id=uid, query="python", config=AgentConfig(**cfg))


def test_langgraph_matches_sequential_finish_and_citations() -> None:
    uid = uuid4()
    provider = FakeLLMProvider("answer about python")
    lg = LangGraphAgentRuntime(_toolset(uid), provider, _COUNTER)
    seq = SequentialAgentRuntime(_toolset(uid), provider, _COUNTER)

    lg_resp = asyncio.run(lg.respond(_req(uid)))
    seq_resp = asyncio.run(seq.respond(_req(uid)))

    assert lg_resp.finish_reason == seq_resp.finish_reason
    assert len(lg_resp.citations) == len(seq_resp.citations)


def test_langgraph_max_iterations_guard() -> None:
    uid = uuid4()
    lg = LangGraphAgentRuntime(_toolset(uid), FakeLLMProvider("x"), _COUNTER)
    resp = asyncio.run(lg.respond(_req(uid, max_iterations=0)))
    assert resp.finish_reason == FINISH_MAX_ITERATIONS


def test_langgraph_produces_answer() -> None:
    uid = uuid4()
    lg = LangGraphAgentRuntime(_toolset(uid), FakeLLMProvider("the python answer"), _COUNTER)
    resp = asyncio.run(lg.respond(_req(uid)))
    assert resp.answer
    assert resp.finish_reason == "completed"

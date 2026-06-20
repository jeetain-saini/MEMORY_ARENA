"""Unit tests for agent tools and the tool set."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.application.dto.agent_dto import AgentConfig, AgentState
from app.application.services.agent.tools import (
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)
from app.application.services.agent.toolset import AgentToolSet
from tests.unit._agent_fakes import (
    FakeContextBuilder,
    FakeGraphAwareService,
    FakeRetrievalService,
    make_retrieved,
)


def _state(user_id) -> AgentState:
    return AgentState(user_id=user_id, query="python", config=AgentConfig())


# --- MemorySearchTool ------------------------------------------------------

def test_search_tool_populates_state() -> None:
    uid = uuid4()
    tool = MemorySearchTool(FakeRetrievalService([make_retrieved("I use Python", uid)]))
    state = _state(uid)
    step = asyncio.run(tool.run(state))
    assert step.ok
    assert state.retrieved is not None
    assert len(state.candidates) == 1
    assert state.provenance[state.candidates[0].memory_id] == "hybrid"


def test_search_tool_failure_returns_not_ok() -> None:
    uid = uuid4()
    tool = MemorySearchTool(FakeRetrievalService(raises=True))
    state = _state(uid)
    step = asyncio.run(tool.run(state))
    assert not step.ok
    assert step.error
    assert state.retrieved is None


# --- GraphExpansionTool ----------------------------------------------------

def test_expansion_tool_adds_graph_candidates() -> None:
    uid = uuid4()
    base = [make_retrieved("I use Python", uid)]
    search = MemorySearchTool(FakeRetrievalService(base))
    expand = GraphExpansionTool(FakeGraphAwareService(neighbors=[("Python is typed", uuid4())]))
    state = _state(uid)
    asyncio.run(search.run(state))
    step = asyncio.run(expand.run(state))
    assert step.ok
    assert state.expanded is not None
    graph_ids = [mid for mid, prov in state.provenance.items() if prov == "graph"]
    assert len(graph_ids) == 1
    assert len(state.candidates) == 2  # base + 1 graph neighbor


def test_expansion_without_base_is_not_ok() -> None:
    uid = uuid4()
    expand = GraphExpansionTool(FakeGraphAwareService())
    state = _state(uid)
    step = asyncio.run(expand.run(state))
    assert not step.ok


def test_expansion_failure_returns_not_ok() -> None:
    uid = uuid4()
    search = MemorySearchTool(FakeRetrievalService([make_retrieved("a", uid)]))
    expand = GraphExpansionTool(FakeGraphAwareService(raises=True))
    state = _state(uid)
    asyncio.run(search.run(state))
    step = asyncio.run(expand.run(state))
    assert not step.ok


# --- ContextBuilderTool ----------------------------------------------------

def test_context_tool_builds_from_candidates() -> None:
    uid = uuid4()
    search = MemorySearchTool(FakeRetrievalService([make_retrieved("I use Python", uid)]))
    builder = FakeContextBuilder()
    context = ContextBuilderTool(builder)
    state = _state(uid)
    asyncio.run(search.run(state))
    step = asyncio.run(context.run(state))
    assert step.ok
    assert state.context_package is not None
    # The builder received the pre-retrieved candidates (no second retrieval).
    assert builder.last_retrieved == state.candidates


def test_context_tool_failure_returns_not_ok() -> None:
    uid = uuid4()
    context = ContextBuilderTool(FakeContextBuilder(raises=True))
    state = _state(uid)
    step = asyncio.run(context.run(state))
    assert not step.ok


# --- AgentToolSet ----------------------------------------------------------

def _toolset() -> AgentToolSet:
    return AgentToolSet(
        MemorySearchTool(FakeRetrievalService()),
        GraphExpansionTool(FakeGraphAwareService()),
        ContextBuilderTool(FakeContextBuilder()),
    )


def test_toolset_get_by_name() -> None:
    ts = _toolset()
    assert ts.get("memory_search").name == "memory_search"
    assert ts.get("graph_expansion").name == "graph_expansion"
    assert ts.get("context_builder").name == "context_builder"


def test_toolset_names_and_len() -> None:
    ts = _toolset()
    assert set(ts.names()) == {"memory_search", "graph_expansion", "context_builder"}
    assert len(ts) == 3


def test_toolset_unknown_tool_raises() -> None:
    with pytest.raises(KeyError):
        _toolset().get("nope")

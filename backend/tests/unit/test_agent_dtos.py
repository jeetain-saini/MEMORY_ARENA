"""Unit tests for agent DTOs (defaults, immutability, state mutability)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.dto.agent_dto import (
    FINISH_COMPLETED,
    AgentConfig,
    AgentRequest,
    AgentState,
    AgentStepResult,
    AgentToolCall,
)


def test_agent_config_defaults() -> None:
    cfg = AgentConfig()
    assert cfg.max_iterations == 1
    assert cfg.max_tool_calls == 8
    assert cfg.max_citations == 10
    assert cfg.expand_graph is True


def test_agent_request_defaults_config() -> None:
    req = AgentRequest(user_id=uuid4(), query="hi")
    assert isinstance(req.config, AgentConfig)
    assert req.metadata == {}


def test_agent_request_is_frozen() -> None:
    req = AgentRequest(user_id=uuid4(), query="hi")
    with pytest.raises(Exception):
        req.query = "changed"  # type: ignore[misc]


def test_agent_state_is_mutable_and_defaults_completed() -> None:
    state = AgentState(user_id=uuid4(), query="q", config=AgentConfig())
    assert state.finish_reason == FINISH_COMPLETED
    assert state.terminated is False
    state.iteration += 1
    state.steps.append(AgentStepResult(step="retrieve", ok=True))
    assert state.iteration == 1
    assert len(state.steps) == 1


def test_tool_call_arguments_default_empty() -> None:
    call = AgentToolCall(tool_name="memory_search")
    assert call.arguments == {}

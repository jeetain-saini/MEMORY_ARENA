"""Integration tests for the LangGraphExtractionEngine.

These exercise the real LangGraph StateGraph wiring of the shared extraction
steps. They **skip automatically** when ``langgraph`` is not installed (the
offline default engine is sequential), so CI stays green without the dependency.
With the deterministic provider, the graph must produce the same memories as the
sequential engine — proving the two engines share logic and never diverge.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

pytest.importorskip("langgraph")

from app.application.dto.extraction_dto import ExtractionRequest  # noqa: E402
from app.infrastructure.llm.graphs.extraction_graph import LangGraphExtractionEngine  # noqa: E402
from app.infrastructure.llm.graphs.extraction_steps import WORKFLOW_VERSION  # noqa: E402
from app.infrastructure.llm.graphs.sequential_engine import SequentialExtractionEngine  # noqa: E402
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _request(text: str) -> ExtractionRequest:
    return ExtractionRequest(user_id=uuid4(), raw_text=text)


def test_langgraph_engine_extracts_memories() -> None:
    engine = LangGraphExtractionEngine(DeterministicLLMProvider())
    result = _run(engine.extract_memories(_request("I prefer dark mode. I want to ship the project.")))
    assert result.workflow_version == WORKFLOW_VERSION
    assert len(result.memories) == 2


def test_langgraph_matches_sequential_engine() -> None:
    provider = DeterministicLLMProvider()
    text = "I prefer dark mode. I want to ship the project."
    lg = _run(LangGraphExtractionEngine(provider).extract_memories(_request(text)))
    seq = _run(SequentialExtractionEngine(provider).extract_memories(_request(text)))
    assert [(m.content, m.memory_type, m.importance, m.confidence) for m in lg.memories] == [
        (m.content, m.memory_type, m.importance, m.confidence) for m in seq.memories
    ]

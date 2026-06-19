"""Unit tests for the SequentialExtractionEngine (offline default workflow)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.extraction_dto import ExtractionRequest
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.graphs.extraction_steps import WORKFLOW_VERSION
from app.infrastructure.llm.graphs.sequential_engine import SequentialExtractionEngine
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider


def _run(coro):
    return asyncio.run(coro)


def _engine() -> SequentialExtractionEngine:
    return SequentialExtractionEngine(DeterministicLLMProvider())


def _request(text: str) -> ExtractionRequest:
    return ExtractionRequest(user_id=uuid4(), raw_text=text)


def test_extracts_memories_with_workflow_version() -> None:
    result = _run(_engine().extract_memories(_request("I prefer dark mode. I want to ship the project.")))
    assert result.workflow_version == WORKFLOW_VERSION
    assert len(result.memories) == 2
    assert result.source_chars > 0


def test_empty_or_trivial_text_yields_nothing() -> None:
    assert _run(_engine().extract_memories(_request("hi"))).memories == []
    assert _run(_engine().extract_memories(_request("   "))).memories == []


def test_memory_fields_are_well_formed() -> None:
    result = _run(_engine().extract_memories(_request("I prefer concise answers.")))
    mem = result.memories[0]
    assert mem.memory_type == MemoryType.PREFERENCE
    assert 0.0 <= mem.importance <= 1.0
    assert 0.0 <= mem.confidence <= 1.0
    assert mem.metadata["workflow_version"] == WORKFLOW_VERSION


def test_duplicate_sentences_are_deduped() -> None:
    result = _run(_engine().extract_memories(_request("I ship code. I ship code.")))
    assert len(result.memories) == 1


def test_each_memory_type_is_a_valid_enum() -> None:
    text = "The sky is blue. I want to win. I prefer tea. I can write Cypher. I am building MemoryArena."
    result = _run(_engine().extract_memories(_request(text)))
    assert result.memories
    assert all(isinstance(m.memory_type, MemoryType) for m in result.memories)


def test_workflow_is_deterministic() -> None:
    req = _request("I prefer dark mode. I want to ship the project.")
    first = _run(_engine().extract_memories(req))
    second = _run(_engine().extract_memories(req))
    assert [(m.content, m.memory_type, m.importance, m.confidence) for m in first.memories] == [
        (m.content, m.memory_type, m.importance, m.confidence) for m in second.memories
    ]

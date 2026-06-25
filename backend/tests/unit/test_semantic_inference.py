"""Unit tests for the Phase B SemanticKnowledgeInferenceService.

All tests use fake LLM providers — no API keys, fully deterministic. They cover
the valid path, the type mapping, and every failure -> Phase A fallback branch.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.application.services.inference.semantic_inference import (
    SemanticKnowledgeInferenceService,
)
from app.domain.value_objects.memory_type import MemoryType


class _FakeProvider:
    """Minimal LLMProvider stub returning a canned structured_generate result."""

    def __init__(self, result: Any = None, *, raises: Exception | None = None, hang: bool = False):
        self._result = result
        self._raises = raises
        self._hang = hang

    @property
    def model_name(self) -> str:
        return "fake"

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        return ""

    async def structured_generate(self, prompt, *, schema, system=None) -> dict[str, Any]:
        if self._hang:
            await asyncio.sleep(10)
        if self._raises is not None:
            raise self._raises
        return self._result

    async def health_check(self) -> bool:
        return True


def _run(coro):
    return asyncio.run(coro)


def test_valid_semantic_candidate() -> None:
    provider = _FakeProvider(
        {"candidates": [{
            "memory_type": "skill", "content": "Uses FastAPI", "confidence": 0.93,
            "importance": 0.7, "reason_for_inference": "Built a backend with FastAPI.",
            "topic": "FastAPI", "progression_stage": "uses",
        }]}
    )
    svc = SemanticKnowledgeInferenceService(provider)
    out = _run(svc.infer("We migrated our backend to FastAPI."))
    assert out is not None
    assert out.statement == "Uses FastAPI"
    assert out.memory_type == MemoryType.SKILL
    assert out.confidence == 0.93
    assert out.topic == "FastAPI"
    assert out.progression_stage == "uses"


def test_interest_type_maps_to_preference() -> None:
    provider = _FakeProvider(
        {"candidates": [{"memory_type": "interest", "content": "Interested in Rust",
                         "confidence": 0.6, "importance": 0.4, "reason_for_inference": "Asked about Rust."}]}
    )
    out = _run(SemanticKnowledgeInferenceService(provider).infer("What is Rust?"))
    assert out is not None and out.memory_type == MemoryType.PREFERENCE


def test_malformed_json_falls_back_to_phase_a() -> None:
    # Provider returns a non-dict (simulating unparseable output).
    out = _run(SemanticKnowledgeInferenceService(_FakeProvider("not json")).infer("What is Rust?"))
    assert out is not None  # Phase A handled it
    assert out.statement == "Interested in Rust"


def test_schema_violation_falls_back() -> None:
    # Missing required fields -> invalid -> fallback.
    provider = _FakeProvider({"candidates": [{"memory_type": "skill"}]})
    out = _run(SemanticKnowledgeInferenceService(provider).infer("Teach me Rust."))
    assert out is not None and out.statement == "Learning Rust"


def test_hallucinated_out_of_range_confidence_falls_back() -> None:
    provider = _FakeProvider(
        {"candidates": [{"memory_type": "skill", "content": "Uses Rust", "confidence": 9.9,
                         "importance": 0.5, "reason_for_inference": "x"}]}
    )
    out = _run(SemanticKnowledgeInferenceService(provider).infer("I built a Rust API."))
    assert out is not None and out.statement == "Uses Rust"  # via Phase A


def test_provider_error_falls_back() -> None:
    provider = _FakeProvider(raises=RuntimeError("LLM down"))
    out = _run(SemanticKnowledgeInferenceService(provider).infer("What is FastAPI?"))
    assert out is not None and out.statement == "Interested in FastAPI"


def test_timeout_falls_back() -> None:
    provider = _FakeProvider(hang=True)
    svc = SemanticKnowledgeInferenceService(provider, timeout_s=0.05)
    out = _run(svc.infer("What is Docker?"))
    assert out is not None and out.statement == "Interested in Docker"


def test_unrecognized_turn_returns_none() -> None:
    provider = _FakeProvider({"candidates": []})
    out = _run(SemanticKnowledgeInferenceService(provider).infer("What is the weather today?"))
    assert out is None  # empty LLM + Phase A both decline


def test_rejects_raw_question_content() -> None:
    # Even if the LLM echoes the question as content, validation rejects it.
    provider = _FakeProvider(
        {"candidates": [{"memory_type": "interest", "content": "What is Rust?", "confidence": 0.8,
                         "importance": 0.5, "reason_for_inference": "x"}]}
    )
    out = _run(SemanticKnowledgeInferenceService(provider).infer("What is Rust?"))
    assert out is not None and out.statement == "Interested in Rust"  # fell back, no "?"
    assert "?" not in out.statement

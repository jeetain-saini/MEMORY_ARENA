"""Unit tests for the DeterministicLLMProvider (offline, reproducible)."""

from __future__ import annotations

import asyncio

from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider


def _run(coro):
    return asyncio.run(coro)


def test_generate_normalizes_whitespace() -> None:
    provider = DeterministicLLMProvider()
    assert _run(provider.generate("  hello   world \n")) == "hello world"


def test_structured_generate_is_deterministic() -> None:
    provider = DeterministicLLMProvider()
    schema = {"memory_type": "str", "importance": "float", "confidence": "float"}
    a = _run(provider.structured_generate("I prefer dark mode", schema=schema))
    b = _run(provider.structured_generate("I prefer dark mode", schema=schema))
    assert a == b


def test_memory_worthy_and_candidates() -> None:
    provider = DeterministicLLMProvider()
    worthy = _run(provider.structured_generate("I like tea. I ship code.", schema={"memory_worthy": "bool"}))
    assert worthy["memory_worthy"] is True
    short = _run(provider.structured_generate("hi", schema={"memory_worthy": "bool"}))
    assert short["memory_worthy"] is False
    cands = _run(provider.structured_generate("I like tea. I ship code.", schema={"candidates": "list[str]"}))
    assert len(cands["candidates"]) == 2


def test_classification_uses_keywords() -> None:
    provider = DeterministicLLMProvider()
    out = _run(provider.structured_generate("I prefer concise answers", schema={"memory_type": "str"}))
    assert out["memory_type"] == MemoryType.PREFERENCE.value
    fact = _run(provider.structured_generate("The sky is blue", schema={"memory_type": "str"}))
    assert fact["memory_type"] == MemoryType.FACT.value


def test_scores_in_range_and_confidence_drops_with_hedging() -> None:
    provider = DeterministicLLMProvider()
    confident = _run(provider.structured_generate("I ship code daily", schema={"confidence": "float"}))
    hedged = _run(provider.structured_generate("I think I might ship code", schema={"confidence": "float"}))
    assert 0.0 <= hedged["confidence"] < confident["confidence"] <= 1.0
    imp = _run(provider.structured_generate("This is critical and important", schema={"importance": "float"}))
    assert 0.0 <= imp["importance"] <= 1.0


def test_unknown_schema_key_is_none() -> None:
    provider = DeterministicLLMProvider()
    out = _run(provider.structured_generate("text", schema={"mystery": "str"}))
    assert out == {"mystery": None}


def test_health_check_true() -> None:
    assert _run(DeterministicLLMProvider().health_check()) is True

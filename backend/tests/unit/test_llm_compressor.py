"""Unit tests for LLMContextCompressor (accept / validate / fallback)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from app.application.dto.context_dto import ContextMemory
from app.application.interfaces.llm_provider import LLMProvider
from app.application.services.context.compressor import HeuristicContextCompressor
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.compressors.llm_compressor import LLMContextCompressor
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider

_COUNTER = HeuristicTokenCounter()


def _cm(content: str, score: float = 0.7, memory_type: MemoryType = MemoryType.FACT) -> ContextMemory:
    return ContextMemory(
        memory_id=uuid4(),
        content=content,
        memory_type=memory_type,
        status=MemoryStatus.ACTIVE,
        score=score,
        tokens=_COUNTER.count(content),
    )


class _FakeLLMProvider(LLMProvider):
    """Returns a fixed response, or raises if ``raises`` is set."""

    def __init__(self, response: str = "", *, raises: bool = False) -> None:
        self._response = response
        self._raises = raises
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "fake"

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if self._raises:
            raise RuntimeError("provider down")
        return self._response

    async def structured_generate(
        self, prompt: str, *, schema: dict[str, str], system: str | None = None
    ) -> dict[str, Any]:
        return {}

    async def health_check(self) -> bool:
        return True


def _compressor(provider: LLMProvider) -> LLMContextCompressor:
    return LLMContextCompressor(
        provider, _COUNTER, fallback=HeuristicContextCompressor(_COUNTER)
    )


# -- accept path ------------------------------------------------------------

def test_uses_llm_output_when_valid() -> None:
    provider = _FakeLLMProvider("[fact] paris is the capital of france")
    memories = [_cm("Paris is the capital of France")]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=1000))
    assert result.context_text == "[fact] paris is the capital of france"
    assert result.stats.removed_memories == 0
    assert provider.calls == 1


def test_preserves_provenance_on_llm_path() -> None:
    provider = _FakeLLMProvider("[fact] a\n[goal] b")
    m1 = _cm("alpha fact", memory_type=MemoryType.FACT)
    m2 = _cm("beta goal", memory_type=MemoryType.GOAL)
    result = asyncio.run(_compressor(provider).compress([m1, m2], max_tokens=1000))
    ids = {m.memory_id for m in result.memories}
    types = {m.memory_type for m in result.memories}
    assert ids == {m1.memory_id, m2.memory_id}
    assert types == {MemoryType.FACT, MemoryType.GOAL}


def test_ratio_computed_on_llm_path() -> None:
    provider = _FakeLLMProvider("[fact] short")
    memories = [_cm("a much longer original memory body that is quite verbose indeed")]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=1000))
    assert result.stats.compressed_tokens <= result.stats.original_tokens
    assert 0.0 < result.stats.ratio <= 1.0


# -- fallback paths ---------------------------------------------------------

def test_falls_back_on_empty_response() -> None:
    provider = _FakeLLMProvider("")
    memories = [_cm("Paris is the capital", memory_type=MemoryType.FACT)]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=1000))
    # Heuristic fallback rendered the content itself.
    assert "Paris is the capital" in result.context_text


def test_falls_back_on_provider_exception() -> None:
    provider = _FakeLLMProvider(raises=True)
    memories = [_cm("Paris is the capital", memory_type=MemoryType.FACT)]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=1000))
    assert "Paris is the capital" in result.context_text


def test_falls_back_on_budget_exceeded() -> None:
    provider = _FakeLLMProvider("[fact] " + "verbose " * 200)
    memories = [_cm("Paris is the capital", memory_type=MemoryType.FACT)]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=5))
    assert result.stats.compressed_tokens <= 5


def test_falls_back_on_missing_section() -> None:
    # Response omits the [goal] marker → required-section validation fails.
    provider = _FakeLLMProvider("ship the product without any markers at all")
    memories = [_cm("I want to ship the product", memory_type=MemoryType.GOAL)]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=1000))
    # Fallback renders with (type) marker, not the LLM's marker-less text.
    assert result.context_text != "ship the product without any markers at all"


def test_falls_back_on_dropped_contradiction() -> None:
    provider = _FakeLLMProvider("[fact] user enjoys cooking pasta on weekends")
    memories = [_cm("I no longer use Rust", memory_type=MemoryType.FACT)]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=1000))
    assert "Rust" in result.context_text  # heuristic fallback kept the original


def test_falls_back_on_dropped_goal() -> None:
    provider = _FakeLLMProvider("[goal] user likes coffee in the morning")
    memories = [_cm("I want to ship the product", memory_type=MemoryType.GOAL)]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=1000))
    assert "ship the product" in result.context_text


# -- budget guarantees ------------------------------------------------------

def test_budget_guarantee_llm_path() -> None:
    provider = _FakeLLMProvider("[fact] tiny")
    memories = [_cm("Paris is the capital", memory_type=MemoryType.FACT)]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=1000))
    assert result.stats.compressed_tokens <= 1000


def test_budget_guarantee_fallback_path() -> None:
    provider = _FakeLLMProvider(raises=True)
    memories = [_cm("a b c d e f", 0.9), _cm("g h i j k l", 0.1)]
    budget = _COUNTER.count("a b c d e f")
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=budget))
    assert result.stats.compressed_tokens <= budget


def test_deterministic_provider_triggers_fallback() -> None:
    # The deterministic provider echoes the (huge) prompt → budget_exceeded →
    # fallback. This is the offline-first default path.
    provider = DeterministicLLMProvider()
    memories = [_cm("Paris is the capital", memory_type=MemoryType.FACT)]
    result = asyncio.run(_compressor(provider).compress(memories, max_tokens=20))
    assert result.stats.compressed_tokens <= 20


# -- empty input ------------------------------------------------------------

def test_empty_memories_returns_empty_without_calling_llm() -> None:
    provider = _FakeLLMProvider("should not be used")
    result = asyncio.run(_compressor(provider).compress([], max_tokens=1000))
    assert result.context_text == ""
    assert result.stats.ratio == 1.0
    assert provider.calls == 0

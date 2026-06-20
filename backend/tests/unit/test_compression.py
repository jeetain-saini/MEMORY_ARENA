"""Unit tests for HeuristicContextCompressor."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.services.context.compressor import HeuristicContextCompressor
from app.application.dto.context_dto import ContextMemory
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType

_COUNTER = HeuristicTokenCounter()


def _cm(content: str, score: float) -> ContextMemory:
    return ContextMemory(
        memory_id=uuid4(), content=content, memory_type=MemoryType.FACT,
        status=MemoryStatus.ACTIVE, score=score, tokens=_COUNTER.count(content),
    )


def _compressor() -> HeuristicContextCompressor:
    return HeuristicContextCompressor(_COUNTER)


def test_within_budget_keeps_all() -> None:
    memories = [_cm("alpha beta", 0.9), _cm("gamma delta", 0.8)]
    result = asyncio.run(_compressor().compress(memories, max_tokens=1000))
    assert len(result.memories) == 2
    assert result.stats.removed_memories == 0


def test_whitespace_normalization_reduces_tokens() -> None:
    memory = _cm("hello" + " " * 40 + "world", 0.9)
    result = asyncio.run(_compressor().compress([memory], max_tokens=1000))
    assert result.stats.compressed_tokens < result.stats.original_tokens
    assert result.stats.ratio < 1.0


def test_over_budget_drops_lowest_score() -> None:
    keep = _cm("aaaa bbbb cccc", 0.9)
    drop = _cm("dddd eeee ffff", 0.1)
    budget = _COUNTER.count("aaaa bbbb cccc")
    result = asyncio.run(_compressor().compress([keep, drop], max_tokens=budget))
    assert keep.memory_id in {m.memory_id for m in result.memories}
    assert result.stats.removed_memories == 1
    assert result.removed[0].reason == "compression"


def test_context_text_contains_kept_content() -> None:
    result = asyncio.run(
        _compressor().compress([_cm("paris is the capital", 0.9)], max_tokens=1000)
    )
    assert "paris is the capital" in result.context_text


def test_empty_input_ratio_is_one() -> None:
    result = asyncio.run(_compressor().compress([], max_tokens=1000))
    assert result.stats.ratio == 1.0
    assert result.context_text == ""

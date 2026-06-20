"""Unit tests for the compression prompt architecture."""

from __future__ import annotations

from uuid import uuid4

from app.application.dto.context_dto import ContextMemory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.compressors.compression_prompts import (
    CHARS_PER_TOKEN,
    COMPRESSION_SYSTEM_PROMPT,
    build_compression_prompt,
    char_budget,
    render_memory_lines,
)


def _cm(content: str, memory_type: MemoryType = MemoryType.FACT) -> ContextMemory:
    return ContextMemory(
        memory_id=uuid4(),
        content=content,
        memory_type=memory_type,
        status=MemoryStatus.ACTIVE,
        score=0.7,
        tokens=len(content) // 4,
    )


def test_char_budget_scales_with_tokens() -> None:
    assert char_budget(100) == 100 * CHARS_PER_TOKEN


def test_char_budget_never_zero() -> None:
    assert char_budget(0) >= 1


def test_render_memory_lines_includes_type_markers() -> None:
    lines = render_memory_lines([_cm("ship v1", MemoryType.GOAL), _cm("likes tea", MemoryType.PREFERENCE)])
    assert "[GOAL]" in lines
    assert "[PREFERENCE]" in lines


def test_render_memory_lines_one_line_per_memory() -> None:
    memories = [_cm("a"), _cm("b"), _cm("c")]
    lines = render_memory_lines(memories)
    assert len(lines.splitlines()) == 3


def test_build_prompt_mentions_budget_and_count() -> None:
    prompt = build_compression_prompt([_cm("alpha"), _cm("beta")], max_tokens=50)
    assert "2 memories" in prompt
    assert str(char_budget(50)) in prompt


def test_build_prompt_includes_content() -> None:
    prompt = build_compression_prompt([_cm("paris is the capital")], max_tokens=50)
    assert "paris is the capital" in prompt


def test_system_prompt_demands_contradiction_preservation() -> None:
    assert "contradiction" in COMPRESSION_SYSTEM_PROMPT.lower()

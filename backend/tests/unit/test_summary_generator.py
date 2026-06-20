"""Unit tests for DeterministicSummaryGenerator."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.summaries.deterministic_summary_generator import (
    DeterministicSummaryGenerator,
)


def _mem(content: str) -> Memory:
    return Memory.create(user_id=uuid4(), content=content, memory_type=MemoryType.PROJECT)


def _gen(memories, *, max_chars=1200) -> str:
    generator = DeterministicSummaryGenerator()
    return asyncio.run(generator.generate(MemoryType.PROJECT, memories, max_chars=max_chars))


def test_empty_returns_empty() -> None:
    assert _gen([]) == ""


def test_includes_each_memory_content() -> None:
    text = _gen([_mem("build the api"), _mem("ship the dashboard")])
    assert "build the api" in text
    assert "ship the dashboard" in text


def test_has_scope_header() -> None:
    text = _gen([_mem("alpha")])
    assert text.startswith("Project summary")


def test_respects_char_budget() -> None:
    text = _gen([_mem("x" * 500), _mem("y" * 500)], max_chars=50)
    assert len(text) <= 50


def test_normalizes_whitespace() -> None:
    text = _gen([_mem("messy" + " " * 20 + "content")])
    assert "messy content" in text

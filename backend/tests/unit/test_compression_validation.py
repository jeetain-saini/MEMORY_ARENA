"""Unit tests for LLM compression output validation."""

from __future__ import annotations

from uuid import uuid4

from app.application.dto.context_dto import ContextMemory
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.compressors.compression_validation import (
    validate_contradictions,
    validate_goals,
    validate_llm_output,
    validate_parse,
    validate_required_sections,
    validate_tokens,
)

_COUNTER = HeuristicTokenCounter()


def _cm(content: str, memory_type: MemoryType = MemoryType.FACT) -> ContextMemory:
    return ContextMemory(
        memory_id=uuid4(),
        content=content,
        memory_type=memory_type,
        status=MemoryStatus.ACTIVE,
        score=0.7,
        tokens=_COUNTER.count(content),
    )


# -- parse ------------------------------------------------------------------

def test_parse_rejects_empty() -> None:
    assert not validate_parse("").ok
    assert not validate_parse("   ").ok


def test_parse_accepts_text() -> None:
    assert validate_parse("[fact] something").ok


# -- token ------------------------------------------------------------------

def test_token_rejects_oversized() -> None:
    big = "word " * 500
    result = validate_tokens(big, max_tokens=5, counter=_COUNTER)
    assert not result.ok
    assert result.reason == "budget_exceeded"


def test_token_accepts_within_budget() -> None:
    assert validate_tokens("tiny text", max_tokens=1000, counter=_COUNTER).ok


# -- required sections ------------------------------------------------------

def test_required_sections_pass_when_markers_present() -> None:
    memories = [_cm("ship v1", MemoryType.GOAL), _cm("a fact", MemoryType.FACT)]
    output = "[goal] ship v1\n[fact] a fact"
    assert validate_required_sections(memories, output).ok


def test_required_sections_fail_when_marker_missing() -> None:
    memories = [_cm("ship v1", MemoryType.GOAL)]
    output = "ship v1 with no marker"
    result = validate_required_sections(memories, output)
    assert not result.ok
    assert "goal" in result.reason


# -- contradiction preservation ---------------------------------------------

def test_contradiction_preserved_passes() -> None:
    memories = [_cm("I no longer use Rust", MemoryType.FACT)]
    output = "[fact] user no longer uses rust"
    assert validate_contradictions(memories, output).ok


def test_contradiction_dropped_fails() -> None:
    memories = [_cm("I no longer use Rust", MemoryType.FACT)]
    output = "[fact] user enjoys cooking pasta"
    result = validate_contradictions(memories, output)
    assert not result.ok
    assert result.reason == "contradiction_dropped"


def test_non_negated_memory_ignored_by_contradiction_check() -> None:
    memories = [_cm("I enjoy hiking", MemoryType.FACT)]
    output = "[fact] totally unrelated text here"
    # No negation marker → not subject to the contradiction check.
    assert validate_contradictions(memories, output).ok


# -- goal preservation ------------------------------------------------------

def test_goal_preserved_passes() -> None:
    memories = [_cm("I want to ship the product", MemoryType.GOAL)]
    output = "[goal] user wants to ship the product"
    assert validate_goals(memories, output).ok


def test_goal_dropped_fails() -> None:
    memories = [_cm("I want to ship the product", MemoryType.GOAL)]
    output = "[goal] user likes coffee in the morning"
    result = validate_goals(memories, output)
    assert not result.ok
    assert result.reason == "goal_dropped"


def test_non_goal_ignored_by_goal_check() -> None:
    memories = [_cm("I like coffee", MemoryType.PREFERENCE)]
    output = "[preference] something else entirely"
    assert validate_goals(memories, output).ok


# -- aggregate --------------------------------------------------------------

def test_validate_llm_output_first_failure_wins() -> None:
    memories = [_cm("ship v1", MemoryType.GOAL)]
    # Empty output → parse failure comes first.
    result = validate_llm_output(memories, "", max_tokens=1000, counter=_COUNTER)
    assert not result.ok
    assert result.reason == "empty_response"


def test_validate_llm_output_all_pass() -> None:
    memories = [_cm("I want to ship the product", MemoryType.GOAL)]
    output = "[goal] user wants to ship the product"
    assert validate_llm_output(memories, output, max_tokens=1000, counter=_COUNTER).ok

"""Validation of LLM compression output before it is trusted.

The LLM is never trusted blindly: its response is accepted only if it passes
every check below, otherwise the caller falls back to the heuristic compressor.

Checks (in order):
  1. parse            — non-empty, textual response
  2. token            — fits the token budget
  3. required-section — every input memory type marker is present
  4. contradiction    — every contradicting (negated) memory survives
  5. goal             — every GOAL memory survives

"Survives" means at least one *significant* term from the memory (stopwords and
negation markers removed — reusing the ConflictDetector vocabulary) appears in
the output, so a memory cannot be silently dropped by the summarizer.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.context_dto import ContextMemory
from app.application.interfaces.token_counter import TokenCounter
from app.application.services.context.conflict_detector import (
    NEGATION_MARKERS,
    STOPWORDS,
)
from app.application.services.retrieval.bm25 import tokenize
from app.domain.value_objects.memory_type import MemoryType


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str = ""


_OK = ValidationResult(ok=True)


def _significant_terms(content: str) -> set[str]:
    return {
        token
        for token in tokenize(content)
        if token not in STOPWORDS and token not in NEGATION_MARKERS
    }


def _is_negated(content: str) -> bool:
    return any(token in NEGATION_MARKERS for token in tokenize(content))


def _survives(memory: ContextMemory, output_terms: set[str]) -> bool:
    terms = _significant_terms(memory.content)
    if not terms:
        return True  # nothing distinctive to preserve
    return bool(terms & output_terms)


def validate_parse(output: str) -> ValidationResult:
    if not output or not output.strip():
        return ValidationResult(ok=False, reason="empty_response")
    return _OK


def validate_tokens(
    output: str, max_tokens: int, counter: TokenCounter
) -> ValidationResult:
    if counter.count(output) > max_tokens:
        return ValidationResult(ok=False, reason="budget_exceeded")
    return _OK


def validate_required_sections(
    memories: list[ContextMemory], output: str
) -> ValidationResult:
    lowered = output.lower()
    for memory_type in {m.memory_type for m in memories}:
        marker = f"[{memory_type.value}]"
        if marker not in lowered:
            return ValidationResult(
                ok=False, reason=f"missing_section:{memory_type.value}"
            )
    return _OK


def validate_contradictions(
    memories: list[ContextMemory], output: str
) -> ValidationResult:
    output_terms = set(tokenize(output))
    for memory in memories:
        if _is_negated(memory.content) and not _survives(memory, output_terms):
            return ValidationResult(
                ok=False, reason="contradiction_dropped"
            )
    return _OK


def validate_goals(memories: list[ContextMemory], output: str) -> ValidationResult:
    output_terms = set(tokenize(output))
    for memory in memories:
        if memory.memory_type is MemoryType.GOAL and not _survives(memory, output_terms):
            return ValidationResult(ok=False, reason="goal_dropped")
    return _OK


def validate_llm_output(
    memories: list[ContextMemory],
    output: str,
    max_tokens: int,
    counter: TokenCounter,
) -> ValidationResult:
    """Run all checks; return the first failure or success."""
    for check in (
        lambda: validate_parse(output),
        lambda: validate_tokens(output, max_tokens, counter),
        lambda: validate_required_sections(memories, output),
        lambda: validate_contradictions(memories, output),
        lambda: validate_goals(memories, output),
    ):
        result = check()
        if not result.ok:
            return result
    return _OK

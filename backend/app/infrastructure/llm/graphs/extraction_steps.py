"""Extraction workflow steps — the shared logic of memory extraction.

Six pure(-ish) async steps operate over an ``ExtractionState`` using the
``LLMProvider`` port. Both engines wire these same steps: the sequential engine
runs them in order; the LangGraph engine adds them as graph nodes. Keeping the
logic here (and provider-driven) means the two engines never diverge and no
LangGraph type leaks into the workflow logic.

    1. detect_signals      — is the text memory-worthy at all?
    2. extract_candidates  — segment into candidate statements
    3. classify_types      — assign a MemoryType to each candidate
    4. estimate_importance — [0,1] importance per candidate
    5. estimate_confidence — [0,1] confidence per candidate
    6. validate_output     — clamp, coerce, drop empties, dedupe -> ExtractedMemory
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.application.dto.extraction_dto import ExtractedMemory
from app.application.interfaces.llm_provider import LLMProvider
from app.domain.value_objects.memory_type import MemoryType

# Workflow generation tag (Decision C): bump when the extraction logic changes
# so results from different generations can be traced and compared.
WORKFLOW_VERSION = "extraction-v1"


@dataclass
class ExtractionState:
    raw_text: str
    worthy: bool = False
    candidates: list[str] = field(default_factory=list)
    drafts: list[dict[str, Any]] = field(default_factory=list)
    memories: list[ExtractedMemory] = field(default_factory=list)


def _clamp(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


# --- the six steps --------------------------------------------------------
async def detect_signals(state: ExtractionState, provider: LLMProvider) -> ExtractionState:
    result = await provider.structured_generate(state.raw_text, schema={"memory_worthy": "bool"})
    state.worthy = bool(result.get("memory_worthy"))
    return state


async def extract_candidates(state: ExtractionState, provider: LLMProvider) -> ExtractionState:
    if not state.worthy:
        state.candidates = []
        return state
    result = await provider.structured_generate(state.raw_text, schema={"candidates": "list[str]"})
    candidates = result.get("candidates") or []
    state.candidates = [str(c).strip() for c in candidates if str(c).strip()]
    return state


async def classify_types(state: ExtractionState, provider: LLMProvider) -> ExtractionState:
    drafts: list[dict[str, Any]] = []
    for candidate in state.candidates:
        result = await provider.structured_generate(candidate, schema={"memory_type": "str"})
        drafts.append({"content": candidate, "memory_type": result.get("memory_type")})
    state.drafts = drafts
    return state


async def estimate_importance(state: ExtractionState, provider: LLMProvider) -> ExtractionState:
    for draft in state.drafts:
        result = await provider.structured_generate(draft["content"], schema={"importance": "float"})
        draft["importance"] = result.get("importance")
    return state


async def estimate_confidence(state: ExtractionState, provider: LLMProvider) -> ExtractionState:
    for draft in state.drafts:
        result = await provider.structured_generate(draft["content"], schema={"confidence": "float"})
        draft["confidence"] = result.get("confidence")
    return state


async def validate_output(state: ExtractionState, provider: LLMProvider) -> ExtractionState:
    seen: set[str] = set()
    memories: list[ExtractedMemory] = []
    for draft in state.drafts:
        content = str(draft.get("content", "")).strip()
        if not content:
            continue
        key = content.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            memory_type = MemoryType(draft.get("memory_type"))
        except ValueError:
            memory_type = MemoryType.FACT
        memories.append(
            ExtractedMemory(
                content=content,
                memory_type=memory_type,
                importance=_clamp(draft.get("importance"), 0.5),
                confidence=_clamp(draft.get("confidence"), 0.5),
                metadata={"workflow_version": WORKFLOW_VERSION},
            )
        )
    state.memories = memories
    return state


# Ordered pipeline shared by both engines.
STEPS = (
    detect_signals,
    extract_candidates,
    classify_types,
    estimate_importance,
    estimate_confidence,
    validate_output,
)

"""SemanticKnowledgeInferenceService (Phase B) — LLM-powered inference.

Upgrades the Phase A deterministic layer with a semantic, LLM-driven inference
step that understands natural language ("I've been experimenting with Rust" ->
"Learning Rust") without rigid templates. It sits in the SAME pre-extraction
slot as Phase A and emits the same :class:`InferredKnowledge`, so nothing
downstream changes.

Safety contract (best-effort, never breaks the pipeline):
  * The LLM only ever returns structured JSON; it never writes to the database.
  * EVERY candidate is validated (type, content, confidence/importance bounds,
    reason). Extra/hallucinated fields are ignored.
  * On ANY failure — timeout, invalid JSON, schema violation, empty output, or
    provider error — it transparently falls back to the Phase A deterministic
    engine. The caller cannot tell the difference.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.application.interfaces.llm_provider import LLMProvider
from app.application.services.inference.knowledge_inference import InferredKnowledge
from app.application.services.inference.knowledge_inference import infer as deterministic_infer
from app.domain.value_objects.memory_type import MemoryType

_logger = logging.getLogger("memoryarena.inference")

# Map the 15 conceptual knowledge types onto the 6 persisted MemoryTypes,
# so the semantic engine needs no schema/DB migration for its core.
_TYPE_MAP: dict[str, MemoryType] = {
    "interest": MemoryType.PREFERENCE, "preference": MemoryType.PREFERENCE,
    "habit": MemoryType.PREFERENCE,
    "skill": MemoryType.SKILL, "technology": MemoryType.SKILL, "learning": MemoryType.SKILL,
    "goal": MemoryType.GOAL, "career": MemoryType.GOAL,
    "project": MemoryType.PROJECT,
    "experience": MemoryType.EXPERIENCE, "work": MemoryType.EXPERIENCE,
    "education": MemoryType.EXPERIENCE, "achievement": MemoryType.EXPERIENCE,
    "fact": MemoryType.FACT, "relationship": MemoryType.FACT,
}

_SCHEMA = {"candidates": "list[dict]"}
_SYSTEM = (
    "You extract durable, long-term knowledge about the user from a single "
    "message. Return ONLY JSON of the form "
    '{"candidates":[{"memory_type":str,"content":str,"confidence":float,'
    '"importance":float,"reason_for_inference":str,"topic":str,'
    '"progression_stage":str}]}. Never store the raw question; store the '
    "inferred fact (e.g. 'Interested in Rust', 'Uses FastAPI'). Return an empty "
    "list for greetings, requests, or anything not durable."
)


def _coerce_unit(value: Any, default: float) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if 0.0 <= f <= 1.0 else None  # out-of-range => reject (hallucination)


class SemanticKnowledgeInferenceService:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        timeout_s: float = 8.0,
        fallback: Callable[[str], InferredKnowledge | None] = deterministic_infer,
    ) -> None:
        self._provider = provider
        self._timeout_s = timeout_s
        self._fallback = fallback

    async def infer(self, text: str) -> InferredKnowledge | None:
        """Best-effort semantic inference; falls back to Phase A on any failure."""
        raw = (text or "").strip()
        if not raw:
            return None
        try:
            result = await asyncio.wait_for(
                self._provider.structured_generate(raw, schema=_SCHEMA, system=_SYSTEM),
                timeout=self._timeout_s,
            )
            candidate = self._validate(result)
            if candidate is not None:
                return candidate
        except (TimeoutError, asyncio.TimeoutError):
            _logger.info("semantic_inference.timeout")
        except Exception:  # noqa: BLE001 — inference is best-effort, never breaks chat
            _logger.warning("semantic_inference.error", exc_info=True)
        return self._fallback(raw)

    def _validate(self, result: Any) -> InferredKnowledge | None:
        """Strictly validate the LLM output; return the first valid candidate."""
        if not isinstance(result, dict):
            return None
        candidates = result.get("candidates")
        if not isinstance(candidates, list):
            return None
        for item in candidates:
            if not isinstance(item, dict):
                continue
            mtype = _TYPE_MAP.get(str(item.get("memory_type", "")).strip().lower())
            content = str(item.get("content", "")).strip()
            if mtype is None or not content or content.endswith("?"):
                continue
            confidence = _coerce_unit(item.get("confidence"), 0.6)
            importance = _coerce_unit(item.get("importance"), 0.5)
            if confidence is None or importance is None:
                continue  # out-of-range numbers => treat as hallucination, skip
            reason = str(item.get("reason_for_inference") or item.get("reason") or "").strip()
            if not reason:
                continue
            return InferredKnowledge(
                statement=content,
                memory_type=mtype,
                confidence=confidence,
                importance=importance,
                reason=reason,
                topic=(str(item.get("topic")).strip() or None) if item.get("topic") else None,
                progression_stage=(
                    str(item.get("progression_stage")).strip() or None
                )
                if item.get("progression_stage")
                else None,
            )
        return None

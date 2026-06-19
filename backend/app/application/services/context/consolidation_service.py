"""MemoryConsolidationService — merge duplicates, keep the best.

Processes memories from highest score to lowest. Each memory is compared to the
already-kept set by token Jaccard similarity; if it is near-duplicate of a kept
memory, it is dropped and recorded as merged into that (higher-scored) one. This
guarantees the highest-quality representative of each duplicate cluster survives.
"""

from __future__ import annotations

from app.application.dto.context_dto import (
    ConsolidationRecord,
    ConsolidationResult,
    ContextMemory,
    DroppedMemory,
)
from app.application.services.context._text import jaccard
from app.application.services.retrieval.bm25 import tokenize


class MemoryConsolidationService:
    def __init__(self, dedup_threshold: float = 0.85) -> None:
        self._threshold = dedup_threshold

    def consolidate(self, memories: list[ContextMemory]) -> ConsolidationResult:
        ordered = sorted(memories, key=lambda m: m.score, reverse=True)

        kept: list[ContextMemory] = []
        kept_tokens: list[set[str]] = []
        removed: list[DroppedMemory] = []
        merged: dict[object, list] = {}  # kept_id -> [removed ids]

        for memory in ordered:
            tokens = set(tokenize(memory.content))
            duplicate_of = None
            for representative, rep_tokens in zip(kept, kept_tokens):
                if jaccard(tokens, rep_tokens) >= self._threshold:
                    duplicate_of = representative
                    break

            if duplicate_of is None:
                kept.append(memory)
                kept_tokens.append(tokens)
            else:
                removed.append(
                    DroppedMemory(memory_id=memory.memory_id, content=memory.content, reason="duplicate")
                )
                merged.setdefault(duplicate_of.memory_id, []).append(memory.memory_id)

        records = [
            ConsolidationRecord(kept_memory_id=kept_id, removed_memory_ids=removed_ids, reason="duplicate")
            for kept_id, removed_ids in merged.items()
        ]
        return ConsolidationResult(consolidated=kept, removed=removed, records=records)

"""HeuristicContextCompressor — fit memories to a token budget, render text.

Two-stage, no-LLM compression:
  1. Normalize whitespace in each memory (cheap token savings, no info loss).
  2. If still over budget, drop the lowest-scored memories until it fits.

Then render the surviving memories into the context string. Reports before/after
token counts so callers can see the compression ratio.
"""

from __future__ import annotations

from app.application.dto.context_dto import (
    CompressionResult,
    CompressionStats,
    ContextMemory,
    DroppedMemory,
)
from app.application.interfaces.context_compressor import ContextCompressor
from app.application.interfaces.token_counter import TokenCounter
from app.application.services.context._text import normalize_whitespace


class HeuristicContextCompressor(ContextCompressor):
    def __init__(self, token_counter: TokenCounter) -> None:
        self._counter = token_counter

    async def compress(
        self, memories: list[ContextMemory], max_tokens: int
    ) -> CompressionResult:
        original_tokens = sum(m.tokens for m in memories)

        # 1. Whitespace normalization.
        normalized = [
            self._renormalize(m, normalize_whitespace(m.content)) for m in memories
        ]

        # 2. Budget-driven pruning (highest score wins ties for inclusion).
        normalized.sort(key=lambda m: m.score, reverse=True)
        kept: list[ContextMemory] = []
        removed: list[DroppedMemory] = []
        used = 0
        for memory in normalized:
            if used + memory.tokens <= max_tokens:
                kept.append(memory)
                used += memory.tokens
            else:
                removed.append(
                    DroppedMemory(memory_id=memory.memory_id, content=memory.content, reason="compression")
                )

        context_text = self._render(kept)
        ratio = round(used / original_tokens, 4) if original_tokens else 1.0
        stats = CompressionStats(
            original_tokens=original_tokens,
            compressed_tokens=used,
            ratio=ratio,
            removed_memories=len(removed),
        )
        return CompressionResult(memories=kept, context_text=context_text, stats=stats, removed=removed)

    def _renormalize(self, memory: ContextMemory, new_content: str) -> ContextMemory:
        from dataclasses import replace

        return replace(memory, content=new_content, tokens=self._counter.count(new_content))

    @staticmethod
    def _render(memories: list[ContextMemory]) -> str:
        return "\n".join(f"- ({m.memory_type.value}) {m.content}" for m in memories)

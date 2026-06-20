"""ContextCompressor port — reduces a memory set to fit a token budget.

Stage 8 ships a heuristic compressor (whitespace normalization + budget-driven
pruning). Stage 10 Phase 3 adds an ``LLMContextCompressor`` (summarization) that
implements the same port with no change to the context builder. The port is
``async`` so an implementation may call an ``LLMProvider``; the heuristic
implementation simply does no awaiting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.context_dto import CompressionResult, ContextMemory


class ContextCompressor(ABC):
    @abstractmethod
    async def compress(
        self, memories: list[ContextMemory], max_tokens: int
    ) -> CompressionResult:
        """Compress ``memories`` to fit ``max_tokens`` and render the context text."""

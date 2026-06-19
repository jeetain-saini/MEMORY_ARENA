"""ContextCompressor port — reduces a memory set to fit a token budget.

Stage 8 ships a heuristic compressor (whitespace normalization + budget-driven
pruning). A future ``LLMCompressor`` (summarization) can implement the same port
with no change to the context builder. No LLM calls in this stage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.context_dto import CompressionResult, ContextMemory


class ContextCompressor(ABC):
    @abstractmethod
    def compress(self, memories: list[ContextMemory], max_tokens: int) -> CompressionResult:
        """Compress ``memories`` to fit ``max_tokens`` and render the context text."""

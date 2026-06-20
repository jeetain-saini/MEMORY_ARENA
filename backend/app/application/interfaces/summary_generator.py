"""SummaryGenerator port — produce a summary string from a set of memories.

The offline default (``DeterministicSummaryGenerator``) is extractive and needs
no LLM. A future LLM-backed generator implements the same port; the
``MemorySummaryService`` is unaffected. Async so an implementation may call an
``LLMProvider``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType


class SummaryGenerator(ABC):
    @abstractmethod
    async def generate(
        self, scope: MemoryType, memories: list[Memory], *, max_chars: int
    ) -> str:
        """Return a summary of ``memories`` (already scoped & ranked) within budget."""

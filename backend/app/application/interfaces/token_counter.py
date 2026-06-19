"""TokenCounter port — estimates token usage for budgeting.

Abstracted so the heuristic counter (Stage 8) can be swapped for a model-exact
tokenizer (e.g. tiktoken) without touching selection/compression logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class TokenCounter(ABC):
    @abstractmethod
    def count(self, text: str) -> int:
        """Return the estimated token count of ``text``."""

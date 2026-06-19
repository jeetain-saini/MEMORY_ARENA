"""HeuristicTokenCounter — fast, model-agnostic token estimation.

Uses the well-known ~4-characters-per-token approximation. Good enough for
budgeting; swap for tiktoken behind the TokenCounter port when model-exact
counts are needed.
"""

from __future__ import annotations

import math

from app.application.interfaces.token_counter import TokenCounter


class HeuristicTokenCounter(TokenCounter):
    CHARS_PER_TOKEN = 4

    def count(self, text: str) -> int:
        stripped = text.strip()
        if not stripped:
            return 0
        return max(1, math.ceil(len(stripped) / self.CHARS_PER_TOKEN))

"""DeterministicSummaryGenerator — offline, extractive summaries.

Builds a stable, reproducible summary by listing the (already score-ranked,
scope-filtered, top-N) memory contents under a scope header, normalizing
whitespace, and truncating to a character budget. No LLM, no network — the
offline default for the summarization workflow and the deterministic test path.
"""

from __future__ import annotations

from app.application.interfaces.summary_generator import SummaryGenerator
from app.application.services.context._text import normalize_whitespace
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType


class DeterministicSummaryGenerator(SummaryGenerator):
    async def generate(
        self, scope: MemoryType, memories: list[Memory], *, max_chars: int
    ) -> str:
        if not memories:
            return ""
        header = f"{scope.value.capitalize()} summary ({len(memories)} memories):"
        lines = [header]
        lines.extend(f"- {normalize_whitespace(memory.content)}" for memory in memories)
        return "\n".join(lines)[:max_chars].rstrip()

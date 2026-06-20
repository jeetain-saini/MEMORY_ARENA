"""Prompt architecture for LLM context compression.

Deterministic, structured prompt construction. The output format is fixed: one
bullet per surviving point, each prefixed with the source memory's type marker in
``[TYPE]`` form, so the response is machine-validatable (see
``compression_validation``). The character budget is derived from the token
budget using the same ~4-chars/token ratio the heuristic token counter assumes,
so the model is steered toward — though never trusted to guarantee — the budget.
"""

from __future__ import annotations

from app.application.dto.context_dto import ContextMemory

# Same ratio as HeuristicTokenCounter (~4 chars/token). Used only to translate a
# token budget into a character hint for the prompt; the real guarantee is the
# post-generation token validation, never this hint.
CHARS_PER_TOKEN = 4

COMPRESSION_SYSTEM_PROMPT = (
    "You are a memory compression assistant for an AI agent's long-term memory. "
    "You distill a set of retrieved memories into the smallest faithful context. "
    "Rules you MUST follow:\n"
    "1. Preserve every fact, goal, preference, project, skill, and experience.\n"
    "2. Preserve contradictions — never silently drop a memory that disagrees "
    "with another; keep both sides.\n"
    "3. Prefix every line with the source memory's type marker in square "
    "brackets, e.g. [GOAL] or [FACT].\n"
    "4. Preserve provenance: do not invent facts that were not in the input.\n"
    "5. Stay within the character budget you are given.\n"
    "Output ONLY the compressed lines — no preamble, no commentary, no headings."
)


def char_budget(max_tokens: int) -> int:
    """Translate a token budget into the character hint used in the prompt."""
    return max(1, max_tokens * CHARS_PER_TOKEN)


def render_memory_lines(memories: list[ContextMemory]) -> str:
    """Render the input memories as type-marked, score-annotated lines."""
    return "\n".join(
        f"[{m.memory_type.value.upper()}] (score={m.score:.2f}) {m.content}"
        for m in memories
    )


def build_compression_prompt(memories: list[ContextMemory], max_tokens: int) -> str:
    """Build the user prompt for compressing ``memories`` under ``max_tokens``."""
    budget = char_budget(max_tokens)
    lines = render_memory_lines(memories)
    return (
        f"Compress the following {len(memories)} memories into at most "
        f"{budget} characters. Keep each distinct point on its own line, "
        f"prefixed with its [TYPE] marker.\n\n"
        f"MEMORIES:\n{lines}\n\n"
        f"COMPRESSED CONTEXT:"
    )

"""MemorySelectionService — choose the best memories within a token budget.

Orders retrieved candidates so **promoted** memories come first, then by
descending retrieval score, and greedily admits them until the token budget is
exhausted. Memories that do not fit are dropped (reason ``token_budget``).
Greedy-by-priority keeps the highest-value memories and still lets smaller
lower-ranked memories fill leftover budget.
"""

from __future__ import annotations

from app.application.dto.context_dto import ContextMemory, DroppedMemory, SelectionResult
from app.application.dto.retrieval_dto import RetrievedMemory
from app.application.interfaces.token_counter import TokenCounter


class MemorySelectionService:
    def __init__(self, token_counter: TokenCounter) -> None:
        self._counter = token_counter

    def select(self, candidates: list[RetrievedMemory], max_tokens: int) -> SelectionResult:
        # Promoted first, then by score (both descending).
        ordered = sorted(
            candidates, key=lambda r: (r.is_promoted, r.final_score), reverse=True
        )

        selected: list[ContextMemory] = []
        dropped: list[DroppedMemory] = []
        used = 0
        for candidate in ordered:
            tokens = self._counter.count(candidate.content)
            if used + tokens <= max_tokens:
                selected.append(
                    ContextMemory(
                        memory_id=candidate.memory_id,
                        content=candidate.content,
                        memory_type=candidate.memory_type,
                        status=candidate.status,
                        score=candidate.final_score,
                        tokens=tokens,
                        is_promoted=candidate.is_promoted,
                    )
                )
                used += tokens
            else:
                dropped.append(
                    DroppedMemory(
                        memory_id=candidate.memory_id,
                        content=candidate.content,
                        reason="token_budget",
                    )
                )
        return SelectionResult(selected=selected, dropped=dropped)

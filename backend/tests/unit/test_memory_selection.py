"""Unit tests for MemorySelectionService."""

from __future__ import annotations

from uuid import uuid4

from app.application.dto.retrieval_dto import RetrievedMemory, ScoreBreakdown
from app.application.services.context.selection_service import MemorySelectionService
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


def _rm(content: str, score: float, *, promoted: bool = False) -> RetrievedMemory:
    return RetrievedMemory(
        memory_id=uuid4(), user_id=uuid4(), content=content, memory_type=MemoryType.FACT,
        status=MemoryStatus.ACTIVE, final_score=score, is_promoted=promoted,
        scores=ScoreBreakdown(vector_score=0, bm25_score=0, memory_score=0, recency_score=0, final_score=score),
    )


def _service() -> MemorySelectionService:
    return MemorySelectionService(HeuristicTokenCounter())


def test_selects_within_budget_and_by_score() -> None:
    candidates = [_rm("low score memory", 0.2), _rm("high score memory", 0.9)]
    result = _service().select(candidates, max_tokens=1000)
    assert [m.content for m in result.selected][0] == "high score memory"
    assert result.dropped == []


def test_promoted_memories_come_first() -> None:
    candidates = [_rm("plain high", 0.95), _rm("promoted low", 0.10, promoted=True)]
    result = _service().select(candidates, max_tokens=1000)
    assert result.selected[0].content == "promoted low"


def test_token_budget_drops_overflow() -> None:
    # Each ~4 tokens; budget only fits one.
    candidates = [_rm("aaaa bbbb", 0.9), _rm("cccc dddd", 0.8)]
    result = _service().select(candidates, max_tokens=3)
    assert len(result.selected) == 1
    assert len(result.dropped) == 1
    assert result.dropped[0].reason == "token_budget"


def test_smaller_memory_fills_leftover_budget() -> None:
    big = _rm("this is a fairly long memory that uses many tokens indeed", 0.9)
    small = _rm("tiny", 0.1)
    result = _service().select([big, small], max_tokens=HeuristicTokenCounter().count(big.content) + 1)
    ids = {m.content for m in result.selected}
    assert "tiny" in ids  # leftover budget admits the small one


def test_empty_candidates() -> None:
    result = _service().select([], max_tokens=1000)
    assert result.selected == [] and result.dropped == []

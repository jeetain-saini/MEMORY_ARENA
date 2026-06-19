"""Unit tests for SimpleCrossEncoderReranker."""

from __future__ import annotations

from uuid import uuid4

from app.application.dto.retrieval_dto import RetrievedMemory, ScoreBreakdown
from app.application.services.retrieval.reranker import SimpleCrossEncoderReranker
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


def _candidate(content: str, final: float) -> RetrievedMemory:
    return RetrievedMemory(
        memory_id=uuid4(),
        user_id=uuid4(),
        content=content,
        memory_type=MemoryType.FACT,
        status=MemoryStatus.ACTIVE,
        final_score=final,
        scores=ScoreBreakdown(
            vector_score=0.0, bm25_score=0.0, memory_score=0.0,
            recency_score=0.0, final_score=final,
        ),
    )


def test_overlap_boosts_matching_candidate() -> None:
    reranker = SimpleCrossEncoderReranker(overlap_weight=0.5)
    matching = _candidate("paris is the capital of france", 0.50)
    other = _candidate("completely unrelated content", 0.50)

    result = reranker.rerank("paris france", [other, matching])
    assert result[0].memory_id == matching.memory_id
    assert result[0].final_score > 0.50  # boosted by overlap


def test_empty_query_preserves_order() -> None:
    reranker = SimpleCrossEncoderReranker()
    a = _candidate("a", 0.9)
    b = _candidate("b", 0.1)
    assert reranker.rerank("", [a, b]) == [a, b]


def test_breakdown_final_is_updated() -> None:
    reranker = SimpleCrossEncoderReranker(overlap_weight=0.5)
    [out] = reranker.rerank("paris", [_candidate("paris", 0.4)])
    assert out.final_score == out.scores.final_score
    assert out.final_score > 0.4

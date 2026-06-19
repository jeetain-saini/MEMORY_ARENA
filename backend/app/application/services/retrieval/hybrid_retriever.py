"""HybridRetriever — weighted fusion of vector, BM25, memory, and recency.

Runs the vector and keyword retrievers concurrently, unions their candidates by
memory id, and computes a final score:

    final = w_vector·vector + w_bm25·bm25 + w_memory·memory + w_recency·recency

Vector scores are cosine (clamped to [0,1]); BM25 scores are min-max normalized
across the candidate set; memory and recency scores are already in [0,1].
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from app.application.dto.retrieval_dto import (
    MemorySearchQuery,
    RetrievedMemory,
    ScoreBreakdown,
)
from app.application.services.retrieval.config import RetrievalConfig
from app.application.services.retrieval.keyword_retriever import KeywordRetriever
from app.application.services.retrieval.scoring import (
    clamp01,
    memory_boost_score,
    recency_score,
)
from app.application.services.retrieval.vector_retriever import VectorRetriever
from app.domain.entities.memory import Memory


class HybridRetriever:
    def __init__(
        self,
        vector_retriever: VectorRetriever,
        keyword_retriever: KeywordRetriever,
        config: RetrievalConfig,
    ) -> None:
        self._vector = vector_retriever
        self._keyword = keyword_retriever
        self._config = config

    async def retrieve(
        self, query: MemorySearchQuery, *, now: datetime | None = None
    ) -> list[RetrievedMemory]:
        now = now or datetime.now(timezone.utc)
        pool = self._config.candidate_pool

        vector_hits, keyword_hits = await asyncio.gather(
            self._vector.retrieve(query, limit=pool),
            self._keyword.retrieve(query, limit=pool),
        )

        vector_scores: dict[UUID, float] = {s.memory.id: s.score for s in vector_hits}
        bm25_raw: dict[UUID, float] = {s.memory.id: s.score for s in keyword_hits}
        memories: dict[UUID, Memory] = {s.memory.id: s.memory for s in vector_hits}
        memories.update({s.memory.id: s.memory for s in keyword_hits})

        max_bm25 = max(bm25_raw.values(), default=0.0)
        cfg = self._config

        results: list[RetrievedMemory] = []
        for memory_id, memory in memories.items():
            vector_score = clamp01(vector_scores.get(memory_id, 0.0))
            bm25_score = (bm25_raw.get(memory_id, 0.0) / max_bm25) if max_bm25 > 0 else 0.0
            mem_score = memory_boost_score(memory, cfg)
            rec_score = recency_score(memory.updated_at, now, cfg.recency_half_life_days)

            final = (
                cfg.weight_vector * vector_score
                + cfg.weight_bm25 * bm25_score
                + cfg.weight_memory * mem_score
                + cfg.weight_recency * rec_score
            )
            results.append(
                RetrievedMemory(
                    memory_id=memory.id,
                    user_id=memory.user_id,
                    content=memory.content,
                    memory_type=memory.memory_type,
                    status=memory.status,
                    final_score=round(final, 6),
                    is_promoted=memory.is_promoted,
                    priority=memory.priority,
                    scores=ScoreBreakdown(
                        vector_score=round(vector_score, 6),
                        bm25_score=round(bm25_score, 6),
                        memory_score=round(mem_score, 6),
                        recency_score=round(rec_score, 6),
                        final_score=round(final, 6),
                    ),
                )
            )

        results.sort(key=lambda r: r.final_score, reverse=True)
        return results

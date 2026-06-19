"""KeywordRetriever — lexical candidate retrieval via BM25.

Builds a per-query corpus from each memory's content and its metadata values,
then ranks with Okapi BM25. Only positively-matching documents are returned;
fusion supplies the rest of the candidate union from the vector side.
"""

from __future__ import annotations

from collections.abc import Callable

from app.application.dto.retrieval_dto import MemorySearchQuery, ScoredMemory
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.retrieval.bm25 import bm25_scores, tokenize
from app.application.services.retrieval.config import RetrievalConfig
from app.application.services.retrieval.scoring import passes_filters
from app.domain.entities.memory import Memory


class KeywordRetriever:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        config: RetrievalConfig,
    ) -> None:
        self._uow_factory = uow_factory
        self._config = config

    async def retrieve(self, query: MemorySearchQuery, *, limit: int) -> list[ScoredMemory]:
        if not query.query.strip():
            return []

        async with self._uow_factory() as uow:
            memories = await uow.memories.list_for_analytics(query.user_id)
        memories = [m for m in memories if passes_filters(m, query.filters)]
        if not memories:
            return []

        corpus = [tokenize(self._document_text(m)) for m in memories]
        scores = bm25_scores(
            tokenize(query.query), corpus, k1=self._config.bm25_k1, b=self._config.bm25_b
        )

        scored = [
            ScoredMemory(memory=memory, score=score)
            for memory, score in zip(memories, scores)
            if score > 0.0
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    @staticmethod
    def _document_text(memory: Memory) -> str:
        parts = [memory.content]
        for value in memory.metadata.values():
            parts.append(str(value))
        return " ".join(parts)

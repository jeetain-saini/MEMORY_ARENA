"""MemoryRetrievalService — orchestrates the hybrid retrieval pipeline.

    query -> vector candidates -> keyword candidates -> fusion -> reranking -> results

``search`` returns the top_k results; ``debug`` returns the full reranked
candidate set with per-signal score breakdowns for inspection.
"""

from __future__ import annotations

from app.application.dto.retrieval_dto import MemorySearchQuery, RetrievalResult
from app.application.interfaces.reranker import Reranker
from app.application.services.retrieval.hybrid_retriever import HybridRetriever


class MemoryRetrievalService:
    def __init__(self, hybrid: HybridRetriever, reranker: Reranker) -> None:
        self._hybrid = hybrid
        self._reranker = reranker

    async def search(self, query: MemorySearchQuery) -> RetrievalResult:
        fused = await self._hybrid.retrieve(query)
        reranked = self._reranker.rerank(query.query, fused)
        top = reranked[: query.top_k]
        return RetrievalResult(
            query=query.query, user_id=query.user_id, results=top, count=len(top)
        )

    async def debug(self, query: MemorySearchQuery) -> RetrievalResult:
        """Like ``search`` but returns every reranked candidate with full scores."""
        fused = await self._hybrid.retrieve(query)
        reranked = self._reranker.rerank(query.query, fused)
        return RetrievalResult(
            query=query.query, user_id=query.user_id, results=reranked, count=len(reranked)
        )

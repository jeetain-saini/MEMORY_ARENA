"""MemoryRetrievalService — orchestrates the hybrid retrieval pipeline.

    query -> vector candidates -> keyword candidates -> fusion -> reranking -> results

``search`` returns the top_k results; ``debug`` returns the full reranked
candidate set with per-signal score breakdowns for inspection.
"""

from __future__ import annotations

from app.application.dto.auth_dto import AuthPrincipal
from app.application.dto.retrieval_dto import MemorySearchQuery, RetrievalResult
from app.application.interfaces.clock import Clock
from app.application.interfaces.metrics_sink import MetricsSink
from app.application.interfaces.reranker import Reranker
from app.application.services.authorization import resolve_scope
from app.application.services.retrieval.hybrid_retriever import HybridRetriever


class MemoryRetrievalService:
    def __init__(
        self,
        hybrid: HybridRetriever,
        reranker: Reranker,
        principal: AuthPrincipal | None = None,
        metrics: MetricsSink | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._hybrid = hybrid
        self._reranker = reranker
        self._principal = principal
        self._metrics = metrics
        self._clock = clock

    async def search(self, query: MemorySearchQuery) -> RetrievalResult:
        resolve_scope(self._principal, query.user_id)
        timed = self._metrics is not None and self._clock is not None
        start = self._clock.now() if timed else 0.0
        fused = await self._hybrid.retrieve(query)
        reranked = self._reranker.rerank(query.query, fused)
        top = reranked[: query.top_k]
        if timed:
            self._metrics.observe("retrieval.latency_ms", (self._clock.now() - start) * 1000.0)
        return RetrievalResult(
            query=query.query, user_id=query.user_id, results=top, count=len(top)
        )

    async def debug(self, query: MemorySearchQuery) -> RetrievalResult:
        """Like ``search`` but returns every reranked candidate with full scores."""
        resolve_scope(self._principal, query.user_id)
        fused = await self._hybrid.retrieve(query)
        reranked = self._reranker.rerank(query.query, fused)
        return RetrievalResult(
            query=query.query, user_id=query.user_id, results=reranked, count=len(reranked)
        )

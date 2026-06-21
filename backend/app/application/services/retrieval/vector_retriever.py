"""VectorRetriever — semantic candidate retrieval via a VectorIndex.

Embeds the query, then delegates ranking to a ``VectorIndex`` (scan by default,
pgvector/HNSW in production). The legacy ``(uow_factory, provider)`` signature is
preserved: when no ``index`` is injected it builds a ``BruteForceVectorIndex`` —
identical to the pre-Phase-5 fetch + cosine + top-k — so existing callers and
``vector_search_mode=scan`` behave exactly as before. Optionally records
vector-search latency.
"""

from __future__ import annotations

from collections.abc import Callable

from app.application.dto.retrieval_dto import MemorySearchQuery, ScoredMemory
from app.application.interfaces.clock import Clock
from app.application.interfaces.embedding_provider import EmbeddingProvider
from app.application.interfaces.metrics_sink import MetricsSink
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.interfaces.vector_index import VectorIndex
from app.application.services.retrieval.brute_force_index import BruteForceVectorIndex


class VectorRetriever:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        provider: EmbeddingProvider,
        *,
        index: VectorIndex | None = None,
        metrics: MetricsSink | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._provider = provider
        self._index = index or BruteForceVectorIndex(uow_factory)
        self._metrics = metrics
        self._clock = clock

    async def retrieve(self, query: MemorySearchQuery, *, limit: int) -> list[ScoredMemory]:
        if not query.query.strip():
            return []

        query_vector = await self._provider.embed_text(query.query)
        timed = self._metrics is not None and self._clock is not None
        start = self._clock.now() if timed else 0.0
        results = await self._index.search(
            query.user_id,
            query_vector,
            limit=limit,
            model_name=self._provider.model_name,
            memory_types=query.filters.memory_types,
            statuses=query.filters.statuses,
        )
        if timed:
            self._metrics.observe("vector_search.latency_ms", (self._clock.now() - start) * 1000.0)
        return [ScoredMemory(memory=memory, score=score) for memory, score in results]

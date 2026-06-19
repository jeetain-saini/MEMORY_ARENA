"""VectorRetriever — semantic candidate retrieval via embedding similarity.

Embeds the query with the configured provider, fetches the user's candidate
embeddings, and ranks them by **cosine similarity**. The candidate fetch is
behind the repository port, so a production deployment can swap brute-force
scoring for a pgvector ANN index without changing this class.
"""

from __future__ import annotations

from collections.abc import Callable

from app.application.dto.retrieval_dto import MemorySearchQuery, ScoredMemory
from app.application.interfaces.embedding_provider import EmbeddingProvider
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.retrieval.scoring import cosine_similarity, passes_filters


class VectorRetriever:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        provider: EmbeddingProvider,
    ) -> None:
        self._uow_factory = uow_factory
        self._provider = provider

    async def retrieve(self, query: MemorySearchQuery, *, limit: int) -> list[ScoredMemory]:
        if not query.query.strip():
            return []

        query_vector = await self._provider.embed_text(query.query)
        async with self._uow_factory() as uow:
            candidates = await uow.embeddings.list_candidates(
                query.user_id, model_name=self._provider.model_name
            )

        scored: list[ScoredMemory] = []
        for memory, vector in candidates:
            if not passes_filters(memory, query.filters):
                continue
            scored.append(ScoredMemory(memory=memory, score=cosine_similarity(query_vector, vector)))

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

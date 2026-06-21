"""BruteForceVectorIndex — exact in-Python cosine over the candidate set.

The default ``VectorIndex`` (``vector_search_mode=scan``) and the offline/test
implementation. It loads the user's candidate embeddings via the repository port
and ranks them with the shared ``rank_candidates`` helper — i.e. exactly what
``VectorRetriever`` did before Phase 5, so behavior is unchanged. Works on every
dialect; it is the fallback the pgvector adapter degrades to off PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.dto.retrieval_dto import RetrievalFilters
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.interfaces.vector_index import VectorIndex
from app.application.services.retrieval.scoring import rank_candidates
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


class BruteForceVectorIndex(VectorIndex):
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def search(
        self,
        user_id: UUID,
        query_vector: list[float],
        *,
        limit: int,
        model_name: str | None = None,
        memory_types: list[MemoryType] | None = None,
        statuses: list[MemoryStatus] | None = None,
    ) -> list[tuple[Memory, float]]:
        async with self._uow_factory() as uow:
            candidates = await uow.embeddings.list_candidates(user_id, model_name=model_name)
        filters = RetrievalFilters(memory_types=memory_types, statuses=statuses)
        return rank_candidates(candidates, query_vector, filters, limit)

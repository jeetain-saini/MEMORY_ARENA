"""PgVectorIndex — the HNSW-ready production VectorIndex seam.

Delegates ranking to the repository's ``search_similar``, which pushes the top-k
down to pgvector (``ORDER BY vector <=> :q``) on PostgreSQL and falls back to the
exact brute-force scan on other dialects (so SQLite stays deterministic). The
optional HNSW index only accelerates the PostgreSQL path — no schema migration is
required for this seam (deferred).

Not exercised by the offline suite on the PostgreSQL path (no live PG); the
brute-force fallback is, and guarantees parity via the shared ranking helper.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.interfaces.vector_index import VectorIndex
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


class PgVectorIndex(VectorIndex):
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
            return await uow.embeddings.search_similar(
                user_id, query_vector, limit=limit, model_name=model_name,
                memory_types=memory_types, statuses=statuses,
            )

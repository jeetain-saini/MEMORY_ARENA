"""VectorIndex port — top-k semantic candidate search.

The seam between ``VectorRetriever`` and *how* nearest neighbors are found:
brute-force scan (default, exact, all dialects) or a pgvector/HNSW pushdown
(production). Returns ``(Memory, cosine_score)`` pairs already ranked + limited,
so swapping the implementation never touches the retriever, fusion, or the API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


class VectorIndex(ABC):
    @abstractmethod
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
        """Return the top-``limit`` (memory, cosine_score) for ``user_id``."""

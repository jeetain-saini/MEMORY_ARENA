"""Repository ports (interfaces) for the memory domain.

These abstract base classes are the PORTS the application depends on. They
speak purely in domain entities and DTOs; they say nothing about Postgres,
Neo4j, or Redis. Concrete adapters in ``app.repositories`` (Stage 3) implement
them, and the API composition root injects those implementations.

Methods are async because every real implementation performs I/O. No
implementation lives here — Stage 2 is contracts only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.embedding_dto import EmbeddingRecord
from app.application.dto.memory_dto import MemorySearchRequest
from app.domain.entities.memory import Memory
from app.domain.entities.memory_relation import MemoryRelation
from app.domain.entities.memory_version import MemoryVersion
from app.domain.entities.user import User
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


class UserRepository(ABC):
    """Persistence port for user accounts (identity + credentials)."""

    @abstractmethod
    async def add(self, user: User) -> User: ...

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...


class MemoryRepository(ABC):
    """Persistence port for the Memory aggregate."""

    @abstractmethod
    async def save(self, memory: Memory) -> Memory: ...

    @abstractmethod
    async def get_by_id(self, memory_id: UUID) -> Memory | None: ...

    @abstractmethod
    async def update(self, memory: Memory) -> Memory: ...

    @abstractmethod
    async def delete(self, memory_id: UUID) -> None: ...

    @abstractmethod
    async def search(self, request: MemorySearchRequest) -> list[Memory]: ...

    @abstractmethod
    async def list_by_user(
        self, user_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Memory]: ...

    @abstractmethod
    async def list_for_analytics(self, user_id: UUID | None = None) -> list[Memory]:
        """Return all non-deleted memories (optionally for one user) for analytics."""

    @abstractmethod
    async def record_retrievals(self, memory_ids: list[UUID]) -> None:
        """Bulk-increment retrieval_count + set last_retrieved_at (Stage 17).

        Lightweight, fire-and-forget read-side signal; does not touch updated_at
        or emit events. A no-op for an empty id list.
        """


class MemoryRelationRepository(ABC):
    """Persistence port for edges in the memory graph."""

    @abstractmethod
    async def save(self, relation: MemoryRelation) -> MemoryRelation: ...

    @abstractmethod
    async def get_by_id(self, relation_id: UUID) -> MemoryRelation | None: ...

    @abstractmethod
    async def delete(self, relation_id: UUID) -> None: ...

    @abstractmethod
    async def list_for_memory(self, memory_id: UUID) -> list[MemoryRelation]: ...


class MemoryVersionRepository(ABC):
    """Append-only history port for memory versions."""

    @abstractmethod
    async def save(self, version: MemoryVersion) -> MemoryVersion: ...

    @abstractmethod
    async def list_for_memory(self, memory_id: UUID) -> list[MemoryVersion]: ...

    @abstractmethod
    async def get_version(self, memory_id: UUID, version_number: int) -> MemoryVersion | None: ...


class MemoryEmbeddingRepository(ABC):
    """Persistence port for memory embeddings (pgvector-backed)."""

    @abstractmethod
    async def save_embedding(self, embedding: EmbeddingRecord) -> EmbeddingRecord:
        """Insert or replace the embedding for (memory_id, model_name)."""

    @abstractmethod
    async def get_embedding(
        self, memory_id: UUID, model_name: str | None = None
    ) -> EmbeddingRecord | None:
        """Return the embedding for a memory (newest if model_name omitted)."""

    @abstractmethod
    async def update_embedding(self, embedding: EmbeddingRecord) -> EmbeddingRecord:
        """Update (or insert) the embedding for (memory_id, model_name)."""

    @abstractmethod
    async def delete_embedding(self, memory_id: UUID) -> None:
        """Delete all embeddings for a memory."""

    @abstractmethod
    async def list_candidates(
        self, user_id: UUID, model_name: str | None = None
    ) -> list[tuple[Memory, list[float]]]:
        """Return (memory, vector) pairs for a user's non-deleted memories.

        Used by vector retrieval to score candidates. (A production deployment
        may push this down to a pgvector ANN index; the port stays the same.)
        """

    @abstractmethod
    async def search_similar(
        self,
        user_id: UUID,
        query_vector: list[float],
        *,
        limit: int,
        model_name: str | None = None,
        memory_types: list[MemoryType] | None = None,
        statuses: list[MemoryStatus] | None = None,
    ) -> list[tuple[Memory, float]]:
        """Top-k (memory, cosine_score) for a user (Stage 14 Phase 5).

        On PostgreSQL this pushes the ranking down to pgvector (``ORDER BY <=>``,
        HNSW-ready); on other dialects it falls back to an exact brute-force scan
        identical to ``list_candidates`` + cosine, so the result is the same.
        """

"""UnitOfWork port — an atomic transactional boundary over the repositories.

A use case opens one Unit of Work, performs work through its repositories, and
either ``commit`` s (all changes persist) or ``rollback`` s (none do). Because
all repositories share the UoW's session, a multi-entity operation — e.g.
"snapshot a version AND update the memory" — is one atomic transaction.

This is an abstraction; the SQLAlchemy implementation lives in the
infrastructure layer. Use cases depend only on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from app.application.interfaces.repositories import (
    MemoryEmbeddingRepository,
    MemoryRelationRepository,
    MemoryRepository,
    MemoryVersionRepository,
)
from app.application.interfaces.summary_repository import MemorySummaryRepository


class UnitOfWork(ABC):
    """Async context manager exposing the repositories of one transaction."""

    memories: MemoryRepository
    relations: MemoryRelationRepository
    versions: MemoryVersionRepository
    embeddings: MemoryEmbeddingRepository
    summaries: MemorySummaryRepository

    @abstractmethod
    async def __aenter__(self) -> "UnitOfWork": ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...

"""SQLAlchemyUnitOfWork — the async, session-scoped Unit of Work.

Entering the context opens a fresh ``AsyncSession`` and constructs the three
repositories bound to it. Leaving the context rolls back if the block did not
commit (or raised) and always closes the session — so a forgotten commit never
silently persists partial work.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.interfaces.unit_of_work import UnitOfWork
from app.repositories.memory_embedding_repository import MemoryEmbeddingRepositoryImpl
from app.repositories.memory_relation_repository import MemoryRelationRepositoryImpl
from app.repositories.memory_repository import MemoryRepositoryImpl
from app.repositories.memory_summary_repository import MemorySummaryRepositoryImpl
from app.repositories.memory_version_repository import MemoryVersionRepositoryImpl


class SQLAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SQLAlchemyUnitOfWork":
        self._session = self._session_factory()
        self.memories = MemoryRepositoryImpl(self._session)
        self.relations = MemoryRelationRepositoryImpl(self._session)
        self.versions = MemoryVersionRepositoryImpl(self._session)
        self.embeddings = MemoryEmbeddingRepositoryImpl(self._session)
        self.summaries = MemorySummaryRepositoryImpl(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
        finally:
            assert self._session is not None
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None
        await self._session.commit()

    async def rollback(self) -> None:
        assert self._session is not None
        await self._session.rollback()

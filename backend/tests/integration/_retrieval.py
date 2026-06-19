"""Helpers for retrieval integration tests (seed memories + embeddings)."""

from __future__ import annotations

from collections.abc import Callable

from app.application.services.embedding_service import EmbeddingService
from app.domain.entities.memory import Memory
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.embeddings.deterministic_provider import DeterministicEmbeddingProvider

DIMS = 16


def make_provider() -> DeterministicEmbeddingProvider:
    return DeterministicEmbeddingProvider(dimensions=DIMS)


def make_uow_factory(engine) -> Callable[[], SQLAlchemyUnitOfWork]:
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    return uow_factory


async def save_and_embed(uow_factory, provider, memory: Memory) -> None:
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    await EmbeddingService(uow_factory, provider).store_embedding(memory)

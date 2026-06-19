"""MemoryEmbeddingRepositoryImpl — pgvector-backed embedding storage.

Implements the Stage 6 port using async SQLAlchemy. ``save``/``update`` are
upsert-style keyed on (memory_id, model_name): re-embedding a memory replaces
its vector rather than violating the unique constraint, which makes the
event-driven pipeline naturally idempotent. The repository never commits — the
Unit of Work owns the transaction.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.embedding_dto import EmbeddingRecord
from app.application.interfaces.repositories import MemoryEmbeddingRepository
from app.infrastructure.database.mappers import embedding_to_model, model_to_embedding
from app.infrastructure.database.models.memory_embedding import MemoryEmbeddingModel


class MemoryEmbeddingRepositoryImpl(MemoryEmbeddingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_embedding(self, embedding: EmbeddingRecord) -> EmbeddingRecord:
        existing = await self._get_model(embedding.memory_id, embedding.model_name)
        if existing is not None:
            existing.vector = list(embedding.vector)
            existing.dimensions = embedding.dimensions
        else:
            self._session.add(embedding_to_model(embedding))
        await self._session.flush()
        return embedding

    async def update_embedding(self, embedding: EmbeddingRecord) -> EmbeddingRecord:
        # Idempotent upsert (re-embedding should not fail if the row is missing).
        return await self.save_embedding(embedding)

    async def get_embedding(
        self, memory_id: uuid.UUID, model_name: str | None = None
    ) -> EmbeddingRecord | None:
        stmt = select(MemoryEmbeddingModel).where(MemoryEmbeddingModel.memory_id == memory_id)
        if model_name is not None:
            stmt = stmt.where(MemoryEmbeddingModel.model_name == model_name)
        stmt = stmt.order_by(MemoryEmbeddingModel.created_at.desc())
        model = await self._session.scalar(stmt)
        return model_to_embedding(model) if model is not None else None

    async def delete_embedding(self, memory_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(MemoryEmbeddingModel).where(MemoryEmbeddingModel.memory_id == memory_id)
        )
        await self._session.flush()

    async def _get_model(
        self, memory_id: uuid.UUID, model_name: str
    ) -> MemoryEmbeddingModel | None:
        stmt = select(MemoryEmbeddingModel).where(
            MemoryEmbeddingModel.memory_id == memory_id,
            MemoryEmbeddingModel.model_name == model_name,
        )
        return await self._session.scalar(stmt)

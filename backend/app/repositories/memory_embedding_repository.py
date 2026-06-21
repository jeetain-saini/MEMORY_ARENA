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
from sqlalchemy.orm import selectinload

from app.application.dto.embedding_dto import EmbeddingRecord
from app.application.dto.retrieval_dto import RetrievalFilters
from app.application.interfaces.repositories import MemoryEmbeddingRepository
from app.application.services.retrieval.scoring import rank_candidates
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.mappers import (
    embedding_to_model,
    model_to_embedding,
    model_to_memory,
)
from app.infrastructure.database.models.memory import MemoryModel
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

    async def list_candidates(
        self, user_id: uuid.UUID, model_name: str | None = None
    ) -> list[tuple[Memory, list[float]]]:
        stmt = (
            select(MemoryModel, MemoryEmbeddingModel.vector)
            .join(MemoryEmbeddingModel, MemoryEmbeddingModel.memory_id == MemoryModel.id)
            .options(selectinload(MemoryModel.score))
            .where(MemoryModel.user_id == user_id, MemoryModel.deleted_at.is_(None))
        )
        if model_name is not None:
            stmt = stmt.where(MemoryEmbeddingModel.model_name == model_name)
        rows = await self._session.execute(stmt)
        return [(model_to_memory(memory), list(vector)) for memory, vector in rows.all()]

    async def search_similar(
        self,
        user_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int,
        model_name: str | None = None,
        memory_types: list[MemoryType] | None = None,
        statuses: list[MemoryStatus] | None = None,
    ) -> list[tuple[Memory, float]]:
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            return await self._search_pgvector(
                user_id, query_vector, limit=limit, model_name=model_name,
                memory_types=memory_types, statuses=statuses,
            )
        # Non-PostgreSQL (e.g. SQLite in tests): exact brute-force fallback,
        # identical to BruteForceVectorIndex.
        candidates = await self.list_candidates(user_id, model_name=model_name)
        filters = RetrievalFilters(memory_types=memory_types, statuses=statuses)
        return rank_candidates(candidates, query_vector, filters, limit)

    async def _search_pgvector(
        self,
        user_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int,
        model_name: str | None,
        memory_types: list[MemoryType] | None,
        statuses: list[MemoryStatus] | None,
    ) -> list[tuple[Memory, float]]:
        # pgvector cosine distance operator (<=>); cosine_similarity = 1 - distance.
        # Uses the HNSW index when present (ORDER BY <=> ... LIMIT), exact otherwise.
        distance = MemoryEmbeddingModel.vector.op("<=>")(query_vector)
        effective_statuses = statuses or [MemoryStatus.ACTIVE]
        stmt = (
            select(MemoryModel, (1 - distance).label("score"))
            .join(MemoryEmbeddingModel, MemoryEmbeddingModel.memory_id == MemoryModel.id)
            .options(selectinload(MemoryModel.score))
            .where(
                MemoryModel.user_id == user_id,
                MemoryModel.deleted_at.is_(None),
                MemoryModel.status.in_([s.value for s in effective_statuses]),
            )
            .order_by(distance)
            .limit(limit)
        )
        if model_name is not None:
            stmt = stmt.where(MemoryEmbeddingModel.model_name == model_name)
        if memory_types is not None:
            stmt = stmt.where(MemoryModel.memory_type.in_([t.value for t in memory_types]))
        rows = await self._session.execute(stmt)
        return [(model_to_memory(memory), float(score)) for memory, score in rows.all()]

    async def _get_model(
        self, memory_id: uuid.UUID, model_name: str
    ) -> MemoryEmbeddingModel | None:
        stmt = select(MemoryEmbeddingModel).where(
            MemoryEmbeddingModel.memory_id == memory_id,
            MemoryEmbeddingModel.model_name == model_name,
        )
        return await self._session.scalar(stmt)

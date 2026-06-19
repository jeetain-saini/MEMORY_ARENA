"""MemoryRepositoryImpl — SQLAlchemy adapter for the MemoryRepository port.

Implements the Stage 2 ``MemoryRepository`` interface using async SQLAlchemy.
The repository never commits — transaction boundaries belong to the Unit of
Work. It flushes so generated state is visible within the transaction.

``search`` performs simple SQL filtering only (status, type, text ILIKE, and a
weighted-score threshold computed from the *domain's* weights). No vector
search yet — that arrives in Stage 4.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.dto.memory_dto import MemorySearchRequest
from app.application.interfaces.repositories import MemoryRepository
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.infrastructure.database.base import utcnow
from app.infrastructure.database.mappers import (
    apply_memory_to_model,
    apply_score_to_model,
    memory_to_model,
    model_to_memory,
    score_to_model,
)
from app.infrastructure.database.models.memory import MemoryModel
from app.infrastructure.database.models.memory_score import MemoryScoreModel


class MemoryRepositoryImpl(MemoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, memory: Memory) -> Memory:
        model = memory_to_model(memory)
        self._session.add(model)
        await self._session.flush()
        return memory

    async def get_by_id(self, memory_id: uuid.UUID) -> Memory | None:
        model = await self._load(memory_id, include_deleted=False)
        return model_to_memory(model) if model is not None else None

    async def update(self, memory: Memory) -> Memory:
        model = await self._load(memory.id, include_deleted=True)
        if model is None:
            raise LookupError(f"Memory {memory.id} not found")
        apply_memory_to_model(model, memory)
        if model.score is None:
            model.score = score_to_model(memory.id, memory.score)
        else:
            apply_score_to_model(model.score, memory.score)
        await self._session.flush()
        return model_to_memory(model)

    async def delete(self, memory_id: uuid.UUID) -> None:
        """Soft delete — tombstone via ``deleted_at`` and mark status DELETED."""
        model = await self._load(memory_id, include_deleted=True)
        if model is None:
            return
        model.deleted_at = utcnow()
        model.status = "deleted"
        await self._session.flush()

    async def search(self, request: MemorySearchRequest) -> list[Memory]:
        stmt = (
            select(MemoryModel)
            .options(selectinload(MemoryModel.score))
            .where(
                MemoryModel.user_id == request.user_id,
                MemoryModel.deleted_at.is_(None),
            )
        )
        if request.statuses:
            stmt = stmt.where(MemoryModel.status.in_([s.value for s in request.statuses]))
        if request.memory_types:
            stmt = stmt.where(MemoryModel.memory_type.in_([t.value for t in request.memory_types]))
        if request.query:
            stmt = stmt.where(MemoryModel.content.ilike(f"%{request.query}%"))
        if request.min_total_score is not None:
            stmt = stmt.join(MemoryScoreModel).where(
                _weighted_score_expr() >= request.min_total_score
            )

        stmt = stmt.order_by(MemoryModel.created_at.desc()).limit(request.limit).offset(request.offset)
        result = await self._session.scalars(stmt)
        return [model_to_memory(m) for m in result.unique().all()]

    async def list_by_user(
        self, user_id: uuid.UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Memory]:
        stmt = (
            select(MemoryModel)
            .options(selectinload(MemoryModel.score))
            .where(MemoryModel.user_id == user_id, MemoryModel.deleted_at.is_(None))
            .order_by(MemoryModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(stmt)
        return [model_to_memory(m) for m in result.unique().all()]

    async def list_for_analytics(self, user_id: uuid.UUID | None = None) -> list[Memory]:
        stmt = (
            select(MemoryModel)
            .options(selectinload(MemoryModel.score))
            .where(MemoryModel.deleted_at.is_(None))
        )
        if user_id is not None:
            stmt = stmt.where(MemoryModel.user_id == user_id)
        result = await self._session.scalars(stmt)
        return [model_to_memory(m) for m in result.unique().all()]

    # -- internals ----------------------------------------------------------
    async def _load(self, memory_id: uuid.UUID, *, include_deleted: bool) -> MemoryModel | None:
        stmt = (
            select(MemoryModel)
            .options(selectinload(MemoryModel.score))
            .where(MemoryModel.id == memory_id)
        )
        if not include_deleted:
            stmt = stmt.where(MemoryModel.deleted_at.is_(None))
        return await self._session.scalar(stmt)


def _weighted_score_expr():
    """SQL expression mirroring MemoryScore.calculate_total_score()."""
    return (
        MemoryScore.WEIGHT_IMPORTANCE * MemoryScoreModel.importance
        + MemoryScore.WEIGHT_UTILITY * MemoryScoreModel.utility
        + MemoryScore.WEIGHT_FREQUENCY * MemoryScoreModel.frequency
        + MemoryScore.WEIGHT_RECENCY * MemoryScoreModel.recency
        + MemoryScore.WEIGHT_CONFIDENCE * MemoryScoreModel.confidence
    )

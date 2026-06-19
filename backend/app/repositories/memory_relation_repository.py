"""MemoryRelationRepositoryImpl — SQLAlchemy adapter for memory-graph edges."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.repositories import MemoryRelationRepository
from app.domain.entities.memory_relation import MemoryRelation
from app.infrastructure.database.mappers import model_to_relation, relation_to_model
from app.infrastructure.database.models.memory_relation import MemoryRelationModel


class MemoryRelationRepositoryImpl(MemoryRelationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, relation: MemoryRelation) -> MemoryRelation:
        model = relation_to_model(relation)
        self._session.add(model)
        await self._session.flush()
        return relation

    async def get_by_id(self, relation_id: uuid.UUID) -> MemoryRelation | None:
        model = await self._session.get(MemoryRelationModel, relation_id)
        return model_to_relation(model) if model is not None else None

    async def delete(self, relation_id: uuid.UUID) -> None:
        model = await self._session.get(MemoryRelationModel, relation_id)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

    async def list_for_memory(self, memory_id: uuid.UUID) -> list[MemoryRelation]:
        stmt = select(MemoryRelationModel).where(
            or_(
                MemoryRelationModel.source_memory_id == memory_id,
                MemoryRelationModel.target_memory_id == memory_id,
            )
        )
        result = await self._session.scalars(stmt)
        return [model_to_relation(m) for m in result.all()]

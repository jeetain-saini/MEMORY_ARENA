"""MemorySummaryRepositoryImpl — SQLAlchemy adapter for rolling summaries."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.summary_repository import MemorySummaryRepository
from app.domain.entities.memory_summary import MemorySummary
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.mappers import model_to_summary
from app.infrastructure.database.models.memory_summary import MemorySummaryModel


class MemorySummaryRepositoryImpl(MemorySummaryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, summary: MemorySummary) -> MemorySummary:
        model = await self._find(summary.user_id, summary.scope)
        if model is None:
            model = MemorySummaryModel(
                id=summary.id,
                user_id=summary.user_id,
                scope=summary.scope.value,
            )
            self._session.add(model)
        model.summary_text = summary.summary_text
        model.source_memory_ids = [str(mid) for mid in summary.source_memory_ids]
        model.source_count = summary.source_count
        model.version = summary.version
        model.updated_at = summary.updated_at
        await self._session.flush()
        return summary

    async def get(self, user_id: UUID, scope: MemoryType) -> MemorySummary | None:
        model = await self._find(user_id, scope)
        return model_to_summary(model) if model is not None else None

    async def list_for_user(self, user_id: UUID) -> list[MemorySummary]:
        stmt = select(MemorySummaryModel).where(MemorySummaryModel.user_id == user_id)
        result = await self._session.scalars(stmt)
        return [model_to_summary(m) for m in result.all()]

    async def delete(self, user_id: UUID, scope: MemoryType) -> None:
        model = await self._find(user_id, scope)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

    async def _find(self, user_id: UUID, scope: MemoryType) -> MemorySummaryModel | None:
        stmt = select(MemorySummaryModel).where(
            MemorySummaryModel.user_id == user_id,
            MemorySummaryModel.scope == scope.value,
        )
        return await self._session.scalar(stmt)

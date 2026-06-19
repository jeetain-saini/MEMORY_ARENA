"""MemoryVersionRepositoryImpl — append-only history of memory snapshots."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.repositories import MemoryVersionRepository
from app.domain.entities.memory_version import MemoryVersion
from app.infrastructure.database.mappers import model_to_version, version_to_model
from app.infrastructure.database.models.memory_version import MemoryVersionModel


class MemoryVersionRepositoryImpl(MemoryVersionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, version: MemoryVersion) -> MemoryVersion:
        model = version_to_model(version)
        self._session.add(model)
        await self._session.flush()
        return version

    async def list_for_memory(self, memory_id: uuid.UUID) -> list[MemoryVersion]:
        stmt = (
            select(MemoryVersionModel)
            .where(MemoryVersionModel.memory_id == memory_id)
            .order_by(MemoryVersionModel.version_number.asc())
        )
        result = await self._session.scalars(stmt)
        return [model_to_version(m) for m in result.all()]

    async def get_version(
        self, memory_id: uuid.UUID, version_number: int
    ) -> MemoryVersion | None:
        stmt = select(MemoryVersionModel).where(
            MemoryVersionModel.memory_id == memory_id,
            MemoryVersionModel.version_number == version_number,
        )
        model = await self._session.scalar(stmt)
        return model_to_version(model) if model is not None else None

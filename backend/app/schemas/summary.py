"""Pydantic response schema for the memory-summary read API.

Wire contract only — a thin serialization of the ``MemorySummary`` domain entity
(a derived artifact produced by the Stage 11 summarization workflow). No business
logic; mirrors the other read schemas.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.entities.memory_summary import MemorySummary
from app.domain.value_objects.memory_type import MemoryType


class MemorySummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    scope: MemoryType
    summary_text: str
    source_memory_ids: list[UUID]
    source_count: int
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, dto: MemorySummary) -> "MemorySummarySchema":
        return cls.model_validate(dto)

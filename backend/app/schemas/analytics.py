"""Pydantic response schema for memory analytics."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.application.dto.analytics_dto import MemoryAnalytics


class AnalyticsResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_memories: int
    active_memories: int
    archived_memories: int
    promoted_memories: int
    average_score: float
    score_distribution: dict[str, int]

    @classmethod
    def from_dto(cls, dto: MemoryAnalytics) -> "AnalyticsResponseSchema":
        return cls.model_validate(dto)

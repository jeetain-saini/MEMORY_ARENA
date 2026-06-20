"""Pydantic response schema for memory health metrics (Stage 13)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.application.dto.health_dto import MemoryHealth


class MemoryHealthResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID | None
    total_memories: int
    active_memories: int
    archived_memories: int
    promoted_memories: int
    promotion_rate: float
    archive_rate: float
    created_last_7_days: int
    created_last_30_days: int
    average_score: float
    avg_reinforcement_signal: float
    graph_nodes: int
    graph_edges: int
    graph_density: float
    summary_scopes_expected: int
    summary_scopes_present: int
    summary_coverage: float
    notes: dict[str, str]

    @classmethod
    def from_dto(cls, dto: MemoryHealth) -> "MemoryHealthResponseSchema":
        return cls.model_validate(dto)

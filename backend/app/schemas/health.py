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
    contradiction_count: int
    superseded_count: int
    type_distribution: dict[str, int]
    average_importance: float
    average_confidence: float
    forgotten_count: int
    episodic_count: int
    semantic_count: int
    cluster_count: int
    promoted_from_count: int
    average_memory_age_days: float
    retrieval_frequency_stats: dict[str, float]
    importance_distribution: dict[str, int]
    confidence_distribution: dict[str, int]
    notes: dict[str, str]

    @classmethod
    def from_dto(cls, dto: MemoryHealth) -> "MemoryHealthResponseSchema":
        return cls.model_validate(dto)

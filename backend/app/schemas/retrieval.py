"""Pydantic schemas for the retrieval API."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.dto.retrieval_dto import (
    MemorySearchQuery,
    RetrievalFilters,
    RetrievalResult,
    RetrievedMemory,
)
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


class RetrievalFiltersSchema(BaseModel):
    memory_types: list[MemoryType] | None = None
    statuses: list[MemoryStatus] | None = None

    def to_dto(self) -> RetrievalFilters:
        return RetrievalFilters(memory_types=self.memory_types, statuses=self.statuses)


class RetrievalSearchRequestSchema(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    user_id: UUID
    top_k: int = Field(default=10, ge=1, le=100)
    filters: RetrievalFiltersSchema | None = None

    def to_query(self) -> MemorySearchQuery:
        filters = self.filters.to_dto() if self.filters else RetrievalFilters()
        return MemorySearchQuery(
            query=self.query, user_id=self.user_id, filters=filters, top_k=self.top_k
        )


class ScoreBreakdownSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vector_score: float
    bm25_score: float
    memory_score: float
    recency_score: float
    final_score: float


class RetrievedMemorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    memory_id: UUID
    user_id: UUID
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    final_score: float
    scores: ScoreBreakdownSchema

    @classmethod
    def from_dto(cls, dto: RetrievedMemory) -> "RetrievedMemorySchema":
        return cls.model_validate(dto)


class RetrievalResultSchema(BaseModel):
    query: str
    user_id: UUID
    count: int
    results: list[RetrievedMemorySchema]

    @classmethod
    def from_dto(cls, dto: RetrievalResult) -> "RetrievalResultSchema":
        return cls(
            query=dto.query,
            user_id=dto.user_id,
            count=dto.count,
            results=[RetrievedMemorySchema.from_dto(r) for r in dto.results],
        )

"""Pydantic schemas for the Context Assembly API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.dto.context_dto import (
    ContextDebugPackage,
    ContextPackage,
    ContextRequest,
)
from app.application.dto.retrieval_dto import RetrievalFilters
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.schemas.retrieval import RetrievalFiltersSchema


class ContextRequestSchema(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    user_id: UUID
    max_tokens: int = Field(default=2000, ge=1, le=200_000)
    top_k: int = Field(default=20, ge=1, le=200)
    filters: RetrievalFiltersSchema | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_request(self) -> ContextRequest:
        filters = self.filters.to_dto() if self.filters else RetrievalFilters()
        return ContextRequest(
            query=self.query,
            user_id=self.user_id,
            max_tokens=self.max_tokens,
            top_k=self.top_k,
            filters=filters,
            metadata=self.metadata,
        )


class ContextMemorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    memory_id: UUID
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    score: float
    tokens: int
    is_promoted: bool


class ContextPackageSchema(BaseModel):
    query: str
    user_id: UUID
    total_tokens: int
    max_tokens: int
    context_text: str
    memories: list[ContextMemorySchema]
    metadata: dict[str, Any]

    @classmethod
    def from_dto(cls, dto: ContextPackage) -> "ContextPackageSchema":
        return cls(
            query=dto.query,
            user_id=dto.user_id,
            total_tokens=dto.total_tokens,
            max_tokens=dto.max_tokens,
            context_text=dto.context_text,
            memories=[ContextMemorySchema.model_validate(m) for m in dto.memories],
            metadata=dto.metadata,
        )


class DroppedMemorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    memory_id: UUID
    content: str
    reason: str


class ConflictRecordSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    memory_id_a: UUID
    memory_id_b: UUID
    reason: str
    content_a: str
    content_b: str


class ConsolidationRecordSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kept_memory_id: UUID
    removed_memory_ids: list[UUID]
    reason: str


class CompressionStatsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    original_tokens: int
    compressed_tokens: int
    ratio: float
    removed_memories: int


class ContextDebugSchema(BaseModel):
    package: ContextPackageSchema
    selected: list[ContextMemorySchema]
    dropped: list[DroppedMemorySchema]
    conflicts: list[ConflictRecordSchema]
    consolidations: list[ConsolidationRecordSchema]
    compression: CompressionStatsSchema

    @classmethod
    def from_dto(cls, dto: ContextDebugPackage) -> "ContextDebugSchema":
        return cls(
            package=ContextPackageSchema.from_dto(dto.package),
            selected=[ContextMemorySchema.model_validate(m) for m in dto.selected],
            dropped=[DroppedMemorySchema.model_validate(d) for d in dto.dropped],
            conflicts=[ConflictRecordSchema.model_validate(c) for c in dto.conflicts],
            consolidations=[
                ConsolidationRecordSchema.model_validate(r) for r in dto.consolidations
            ],
            compression=CompressionStatsSchema.model_validate(dto.compression),
        )

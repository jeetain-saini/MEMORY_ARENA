"""Pydantic request/response schemas for the memory API.

These are the **wire contract** — the only place pydantic appears. They validate
input (content length, metadata limits, enum membership) and convert to/from the
framework-agnostic application DTOs. Domain entities and DTOs never leak to the
client; these schemas do.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.application.dto.memory_dto import (
    CreateMemoryRequest,
    CreateMemoryResponse,
    MemorySearchRequest,
    UpdateMemoryRequest,
)
from app.application.dto.resolution_dto import ContradictionResolutionResult
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType

MAX_CONTENT_LENGTH = 10_000
MAX_METADATA_KEYS = 50
MAX_METADATA_KEY_LENGTH = 128


def _validate_metadata(value: dict[str, Any]) -> dict[str, Any]:
    if len(value) > MAX_METADATA_KEYS:
        raise ValueError(f"metadata may contain at most {MAX_METADATA_KEYS} keys")
    for key in value:
        if not isinstance(key, str) or len(key) > MAX_METADATA_KEY_LENGTH:
            raise ValueError("metadata keys must be strings up to 128 characters")
    return value


class CreateMemoryRequestSchema(BaseModel):
    user_id: UUID
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    memory_type: MemoryType
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v

    @field_validator("metadata")
    @classmethod
    def _metadata_limits(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _validate_metadata(v)

    def to_dto(self) -> CreateMemoryRequest:
        return CreateMemoryRequest(
            user_id=self.user_id,
            content=self.content,
            memory_type=self.memory_type,
            metadata=self.metadata,
        )


class UpdateMemoryRequestSchema(BaseModel):
    user_id: UUID
    content: str | None = Field(default=None, max_length=MAX_CONTENT_LENGTH)
    metadata: dict[str, Any] | None = None
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("content must not be blank")
        return v

    @field_validator("metadata")
    @classmethod
    def _metadata_limits(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if v is None else _validate_metadata(v)

    @model_validator(mode="after")
    def _require_something(self) -> "UpdateMemoryRequestSchema":
        if self.content is None and self.metadata is None:
            raise ValueError("provide content and/or metadata to update")
        return self

    def to_dto(self, memory_id: UUID) -> UpdateMemoryRequest:
        return UpdateMemoryRequest(
            memory_id=memory_id,
            user_id=self.user_id,
            content=self.content,
            metadata=self.metadata,
            reason=self.reason,
        )


class MemorySearchRequestSchema(BaseModel):
    user_id: UUID
    query: str | None = Field(default=None, max_length=MAX_CONTENT_LENGTH)
    memory_types: list[MemoryType] | None = None
    statuses: list[MemoryStatus] | None = None
    min_total_score: float | None = Field(default=None, ge=0.0, le=1.0)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    def to_dto(self) -> MemorySearchRequest:
        return MemorySearchRequest(
            user_id=self.user_id,
            query=self.query,
            memory_types=self.memory_types,
            statuses=self.statuses,
            min_total_score=self.min_total_score,
            limit=self.limit,
            offset=self.offset,
        )


class MemoryResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    total_score: float
    version: int
    is_promoted: bool
    priority: int
    category: MemoryCategory | None = None
    retrieval_count: int = 0
    created_at: datetime
    updated_at: datetime
    # Phase D: read-only exposure of stored metadata (evidence + inference fields)
    # for the evolution/insights UI. Additive; existing clients ignore it.
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dto(cls, dto: CreateMemoryResponse) -> "MemoryResponseSchema":
        return cls.model_validate(dto)


# --- Contradiction resolution (Stage 16) -----------------------------------
class ResolveContradictionRequestSchema(BaseModel):
    user_id: UUID
    keep_id: UUID = Field(description="The authoritative memory to keep")
    archive_id: UUID = Field(description="The obsolete memory to archive")


class ContradictionResolutionResponseSchema(BaseModel):
    kept: MemoryResponseSchema
    archived: MemoryResponseSchema
    superseded_edge: bool
    contradiction_preserved: bool

    @classmethod
    def from_dto(cls, dto: "ContradictionResolutionResult") -> "ContradictionResolutionResponseSchema":
        return cls(
            kept=MemoryResponseSchema.from_dto(dto.kept),
            archived=MemoryResponseSchema.from_dto(dto.archived),
            superseded_edge=dto.superseded_edge,
            contradiction_preserved=dto.contradiction_preserved,
        )

"""Context Assembly DTOs.

The request/result shapes for building an LLM-ready context package out of
retrieved memories. Plain dataclasses — no pydantic, no ORM, no LLM. The package
carries the assembled text and the memories it was built from; the debug package
adds the full provenance (selected, dropped, conflicts, consolidations, stats).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.application.dto.retrieval_dto import RetrievalFilters
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


@dataclass(frozen=True)
class ContextRequest:
    query: str
    user_id: UUID
    max_tokens: int = 2000
    top_k: int = 20
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextMemory:
    memory_id: UUID
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    score: float
    tokens: int
    is_promoted: bool = False


@dataclass(frozen=True)
class DroppedMemory:
    memory_id: UUID
    content: str
    reason: str  # token_budget | duplicate | compression


@dataclass(frozen=True)
class ConflictRecord:
    memory_id_a: UUID
    memory_id_b: UUID
    reason: str
    content_a: str
    content_b: str


@dataclass(frozen=True)
class ConsolidationRecord:
    kept_memory_id: UUID
    removed_memory_ids: list[UUID]
    reason: str  # duplicate


@dataclass(frozen=True)
class CompressionStats:
    original_tokens: int
    compressed_tokens: int
    ratio: float
    removed_memories: int


@dataclass(frozen=True)
class ContextPackage:
    query: str
    user_id: UUID
    memories: list[ContextMemory]
    context_text: str
    total_tokens: int
    max_tokens: int
    metadata: dict[str, Any] = field(default_factory=dict)


# --- intermediate stage results -------------------------------------------
@dataclass(frozen=True)
class SelectionResult:
    selected: list[ContextMemory]
    dropped: list[DroppedMemory]


@dataclass(frozen=True)
class ConsolidationResult:
    consolidated: list[ContextMemory]
    removed: list[DroppedMemory]
    records: list[ConsolidationRecord]


@dataclass(frozen=True)
class CompressionResult:
    memories: list[ContextMemory]
    context_text: str
    stats: CompressionStats
    removed: list[DroppedMemory]


@dataclass(frozen=True)
class ContextDebugPackage:
    package: ContextPackage
    selected: list[ContextMemory]
    dropped: list[DroppedMemory]
    conflicts: list[ConflictRecord]
    consolidations: list[ConsolidationRecord]
    compression: CompressionStats

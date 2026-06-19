"""Retrieval DTOs — the query and result shapes of the hybrid retrieval engine.

Plain dataclasses (no pydantic, no ORM) so the application layer stays
framework-agnostic; the API maps its schemas to/from these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


@dataclass(frozen=True)
class RetrievalFilters:
    """Optional constraints applied before scoring."""

    memory_types: list[MemoryType] | None = None
    statuses: list[MemoryStatus] | None = None


@dataclass(frozen=True)
class MemorySearchQuery:
    query: str
    user_id: UUID
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    top_k: int = 10


@dataclass(frozen=True)
class ScoreBreakdown:
    """The per-signal scores that compose a result's final score (for debug)."""

    vector_score: float
    bm25_score: float
    memory_score: float
    recency_score: float
    final_score: float


@dataclass(frozen=True)
class RetrievedMemory:
    memory_id: UUID
    user_id: UUID
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    final_score: float
    scores: ScoreBreakdown


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    user_id: UUID
    results: list[RetrievedMemory]
    count: int


@dataclass
class ScoredMemory:
    """Internal carrier: a domain memory paired with a single retriever score."""

    memory: Memory
    score: float

"""Application-layer DTOs for memory operations.

DTOs are the typed contract between the delivery layer (API) and the use cases.
They are deliberately plain dataclasses — no pydantic, no ORM — so the
application layer stays framework-agnostic. The API layer maps its pydantic
request/response schemas to and from these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


@dataclass(frozen=True)
class CreateMemoryRequest:
    user_id: UUID
    content: str
    memory_type: MemoryType
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreateMemoryResponse:
    """Canonical representation of a memory returned by create/update use cases."""

    id: UUID
    user_id: UUID
    content: str
    memory_type: MemoryType
    status: MemoryStatus
    total_score: float
    version: int
    is_promoted: bool
    created_at: datetime
    updated_at: datetime
    priority: int = 0


@dataclass(frozen=True)
class UpdateMemoryRequest:
    memory_id: UUID
    user_id: UUID
    content: str | None = None
    metadata: dict[str, Any] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class MemorySearchRequest:
    user_id: UUID
    query: str | None = None
    memory_types: list[MemoryType] | None = None
    statuses: list[MemoryStatus] | None = None
    min_total_score: float | None = None
    limit: int = 20
    offset: int = 0

"""DTOs for the memory-summarization workflow (Stage 11 Phase C)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SummaryRefreshResult:
    """Outcome of refreshing all scoped summaries for one tenant."""

    user_id: UUID
    created: int
    updated: int
    unchanged: int
    scopes: int

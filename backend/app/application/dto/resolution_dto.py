"""Contradiction-resolution DTOs (Stage 16)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.memory_dto import CreateMemoryResponse


@dataclass(frozen=True)
class ContradictionResolutionResult:
    """Outcome of resolving a CONTRADICTS pair.

    ``kept`` is the authoritative memory; ``archived`` is the obsolete one (now
    ARCHIVED). ``superseded_edge`` is True when a durable SUPERSEDES edge
    (kept -> archived) was written. The CONTRADICTS edge is preserved as history.
    """

    kept: CreateMemoryResponse
    archived: CreateMemoryResponse
    superseded_edge: bool
    contradiction_preserved: bool

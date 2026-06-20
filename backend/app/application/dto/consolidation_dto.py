"""Consolidation DTOs.

Plain dataclasses / enums describing the inputs and outputs of the write-time
memory consolidation workflow.  No framework imports here — ports only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID

from app.domain.value_objects.memory_type import MemoryType


class ConsolidationDecisionType(str, Enum):
    UNIQUE = "unique"         # no significant relationship with any candidate
    SUPERSEDES = "supersedes" # new memory fully replaces the target
    CONTRADICTS = "contradicts"  # new memory conflicts with the target
    MERGE = "merge"           # future: the two should be merged (informational only in Phase 2)


@dataclass(frozen=True)
class ConsolidationCandidate:
    memory_id: UUID
    content: str
    memory_type: MemoryType
    total_score: float
    updated_at: datetime


@dataclass(frozen=True)
class ConsolidationRequest:
    new_memory_id: UUID
    user_id: UUID
    new_content: str
    new_type: MemoryType
    candidates: list[ConsolidationCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class ConsolidationDecision:
    decision_type: ConsolidationDecisionType
    target_id: UUID | None   # None for UNIQUE
    reasoning: str
    confidence: float        # [0.0, 1.0]


@dataclass(frozen=True)
class ConsolidationSummary:
    new_memory_id: UUID
    user_id: UUID
    total_candidates: int
    decisions: list[ConsolidationDecision] = field(default_factory=list)
    workflow_version: str = "consolidation-v1"

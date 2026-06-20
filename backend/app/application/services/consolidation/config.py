"""ConsolidationConfig — tunable thresholds for the write-time consolidation pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsolidationConfig:
    # How many recent ACTIVE memories to compare against (upper bound per job).
    candidate_pool: int = 50

    # Minimum confidence to write a CONTRADICTS graph edge.
    contradict_confidence: float = 0.60

    # Minimum confidence to archive a superseded memory (higher than contradict).
    supersede_confidence: float = 0.80

    workflow_version: str = "consolidation-v1"

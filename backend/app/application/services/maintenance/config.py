"""Configuration for the Stage 11 maintenance workflows."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.value_objects.memory_type import MemoryType


@dataclass(frozen=True)
class MaintenanceConfig:
    # --- relationship inference -------------------------------------------
    inference_confidence_threshold: float = 0.5
    inference_candidate_pool: int = 50

    # --- summarization ----------------------------------------------------
    summary_top_n: int = 10
    summary_max_chars: int = 1200
    summary_scopes: tuple[MemoryType, ...] = field(
        default_factory=lambda: (MemoryType.PROJECT, MemoryType.GOAL, MemoryType.EXPERIENCE)
    )

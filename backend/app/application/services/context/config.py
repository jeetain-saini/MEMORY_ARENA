"""Tunable configuration for the Context Assembly Engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextConfig:
    default_max_tokens: int = 2000
    default_top_k: int = 20
    # Jaccard similarity at/above which two memories are treated as duplicates.
    dedup_threshold: float = 0.85
    # Significant-term overlap at/above which a negated pair is a contradiction.
    conflict_threshold: float = 0.6

"""Tunable configuration for the hybrid retrieval engine.

All weights and parameters live here so retrieval behavior can be tuned (per
environment, or later per tenant) without changing the algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalConfig:
    # --- Fusion weights (need not sum to 1; final stays ~[0,1]) -----------
    weight_vector: float = 0.50
    weight_bm25: float = 0.20
    weight_memory: float = 0.20
    weight_recency: float = 0.10

    # --- Candidate pool fetched from each retriever before fusion ---------
    candidate_pool: int = 50

    # --- Recency boosting -------------------------------------------------
    recency_half_life_days: float = 30.0

    # --- Memory-score boosting (Memory Intelligence signals) --------------
    mem_importance: float = 0.40
    mem_utility: float = 0.30
    mem_frequency: float = 0.30
    promotion_bonus: float = 0.15
    priority_weight: float = 0.10
    priority_cap: int = 5

    # --- BM25 parameters --------------------------------------------------
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    # --- Reranking --------------------------------------------------------
    rerank_overlap_weight: float = 0.25

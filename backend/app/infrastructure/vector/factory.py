"""Vector-index factory — selection by ``VECTOR_SEARCH_MODE`` (Stage 14 Phase 5).

* ``scan`` (default) -> ``BruteForceVectorIndex`` (exact, all dialects).
* ``hnsw`` / ``auto`` -> ``PgVectorIndex`` (pgvector pushdown on PostgreSQL,
  brute-force fallback elsewhere — so offline/SQLite stays exact and deterministic).

Not cached: the index wraps a per-request Unit-of-Work factory.
"""

from __future__ import annotations

from collections.abc import Callable

from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.interfaces.vector_index import VectorIndex
from app.application.services.retrieval.brute_force_index import BruteForceVectorIndex
from app.core.config import get_settings


def build_vector_index(uow_factory: Callable[[], UnitOfWork]) -> VectorIndex:
    if get_settings().vector_search_mode.lower() in ("hnsw", "auto"):
        from app.infrastructure.vector.pgvector_index import PgVectorIndex

        return PgVectorIndex(uow_factory)
    return BruteForceVectorIndex(uow_factory)

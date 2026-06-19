"""Graph repository factory — selects the backend from configuration.

``GRAPH_BACKEND`` chooses the implementation:
  * ``memory`` -> InMemoryGraphRepository (offline default; process-wide singleton)
  * ``neo4j``  -> Neo4jGraphRepository (uses the connected Neo4j driver)

Cached as a singleton so the in-memory graph persists across requests. Call
``build_graph_repository.cache_clear()`` in tests that change configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.graph_repository import GraphRepository
from app.core.config import get_settings
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.graph.neo4j import neo4j_manager
from app.infrastructure.graph.neo4j_graph_repository import Neo4jGraphRepository


@lru_cache(maxsize=1)
def build_graph_repository() -> GraphRepository:
    settings = get_settings()
    if settings.graph_backend.lower() == "neo4j":
        return Neo4jGraphRepository(neo4j_manager)
    return InMemoryGraphRepository()

"""Infrastructure layer - frameworks & drivers (concrete I/O).

Implements the ports defined in `application/interfaces` using real
technology: SQLAlchemy/Postgres, pgvector, Neo4j, Redis, LangChain/LangGraph.
Depends inward; nothing inward depends on it.
Stage 0: structure only - no implementation.
"""
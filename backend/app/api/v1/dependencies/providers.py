"""FastAPI dependency providers (the read side of the composition root).

These thin functions expose the process-wide singletons to route handlers via
`Depends(...)`. Handlers ask for *what they need* (a session, the cache client)
without knowing how it was constructed — keeping the dependency rule intact and
making handlers trivially testable by overriding the provider in tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from neo4j import AsyncDriver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.infrastructure.cache.redis import redis_manager
from app.infrastructure.database.postgres import postgres_manager
from app.infrastructure.graph.neo4j import neo4j_manager


def get_app_settings() -> Settings:
    """Provide the cached application settings."""
    return get_settings()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Provide a transactional async SQLAlchemy session, closed after the request."""
    async with postgres_manager.sessionmaker() as session:
        yield session


def get_redis() -> Redis:
    """Provide the shared async Redis client."""
    return redis_manager.client


def get_neo4j() -> AsyncDriver:
    """Provide the shared async Neo4j driver."""
    return neo4j_manager.driver


# Convenience aliases for annotated dependencies.
SettingsDep = Depends(get_app_settings)
DBSessionDep = Depends(get_db_session)
RedisDep = Depends(get_redis)
Neo4jDep = Depends(get_neo4j)

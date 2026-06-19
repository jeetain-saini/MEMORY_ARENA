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

from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.decay_strategies import DecayStrategy, ExponentialDecayStrategy
from app.application.services.intelligence_config import IntelligenceConfig
from app.application.services.memory_analytics_service import MemoryAnalyticsService
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.application.services.memory_service import MemoryService
from app.core.config import Settings, get_settings
from app.infrastructure.cache.redis import redis_manager
from app.infrastructure.database.postgres import postgres_manager
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import in_process_dispatcher
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


def get_unit_of_work() -> UnitOfWork:
    """Provide a fresh Unit of Work bound to the shared session factory.

    The composition root supplies the SQLAlchemy implementation behind the
    ``UnitOfWork`` abstraction the use cases depend on.
    """
    return SQLAlchemyUnitOfWork(postgres_manager.sessionmaker)


def get_event_dispatcher() -> EventDispatcher:
    """Provide the process-wide in-process event dispatcher (singleton)."""
    return in_process_dispatcher


def get_memory_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
    dispatcher: EventDispatcher = Depends(get_event_dispatcher),
) -> MemoryService:
    """Assemble the MemoryService for a request from its dependencies."""
    return MemoryService(uow, dispatcher)


def get_intelligence_config() -> IntelligenceConfig:
    """Provide the (tunable) intelligence thresholds. Defaults for now."""
    return IntelligenceConfig()


def get_decay_strategy() -> DecayStrategy:
    """Provide the configured recency-decay strategy (default: exponential)."""
    return ExponentialDecayStrategy()


def get_memory_intelligence_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
    dispatcher: EventDispatcher = Depends(get_event_dispatcher),
    config: IntelligenceConfig = Depends(get_intelligence_config),
    decay_strategy: DecayStrategy = Depends(get_decay_strategy),
) -> MemoryIntelligenceService:
    """Assemble the Memory Intelligence Engine for a request."""
    return MemoryIntelligenceService(uow, dispatcher, config, decay_strategy)


def get_memory_analytics_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> MemoryAnalyticsService:
    """Assemble the analytics service for a request."""
    return MemoryAnalyticsService(uow)


# Convenience aliases for annotated dependencies.
SettingsDep = Depends(get_app_settings)
DBSessionDep = Depends(get_db_session)
RedisDep = Depends(get_redis)
Neo4jDep = Depends(get_neo4j)
UnitOfWorkDep = Depends(get_unit_of_work)
EventDispatcherDep = Depends(get_event_dispatcher)
MemoryServiceDep = Depends(get_memory_service)
MemoryIntelligenceServiceDep = Depends(get_memory_intelligence_service)
MemoryAnalyticsServiceDep = Depends(get_memory_analytics_service)

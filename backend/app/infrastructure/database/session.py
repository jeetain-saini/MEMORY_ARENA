"""Async engine and session-factory builders (SQLAlchemy 2.x).

Thin, reusable constructors for the async engine and the
``async_sessionmaker``. The application's long-lived engine is owned by
``PostgresManager`` (Stage 1); these helpers let it — and tests, and Alembic —
build engines/factories consistently. Sessions are created with
``expire_on_commit=False`` so objects remain usable after a Unit-of-Work commit.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    """Build an async engine from application settings."""
    return create_async_engine(
        settings.postgres_url,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout=settings.postgres_pool_timeout,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to ``engine`` (Unit-of-Work friendly)."""
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

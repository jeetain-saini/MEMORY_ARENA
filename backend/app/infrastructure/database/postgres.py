"""PostgreSQL connection manager (async SQLAlchemy engine).

Owns a single async engine + session factory for the process. The engine holds
a connection pool, so this manager is the natural singleton: one pool, created
at startup, disposed at shutdown. No ORM models or repositories live here —
Stage 1 only establishes connectivity and a health probe.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

_logger = logging.getLogger("memoryarena.postgres")


class PostgresManager:
    """Lifecycle owner for the async SQLAlchemy engine and session factory."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    async def connect(self, settings: Settings) -> None:
        if self._engine is not None:
            return
        if settings.is_sqlite:
            # SQLite (free-tier/demo): the Postgres pool knobs don't apply. Use a
            # connection-per-use NullPool against the file so SQLite's own locking
            # handles concurrency; allow cross-thread use for the async driver.
            from sqlalchemy.pool import NullPool

            self._engine = create_async_engine(
                settings.postgres_url,
                connect_args={"check_same_thread": False},
                poolclass=NullPool,
                future=True,
            )
        else:
            self._engine = create_async_engine(
                settings.postgres_url,
                pool_size=settings.postgres_pool_size,
                max_overflow=settings.postgres_max_overflow,
                pool_timeout=settings.postgres_pool_timeout,
                pool_pre_ping=True,  # transparently recycle stale connections
                future=True,
            )
        self._sessionmaker = async_sessionmaker(
            bind=self._engine, expire_on_commit=False, class_=AsyncSession
        )
        _logger.info("postgres.connected", extra={"dialect": "sqlite" if settings.is_sqlite else "postgresql"})

    async def disconnect(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None
            _logger.info("postgres.disconnected")

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("PostgresManager is not connected; call connect() first.")
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError("PostgresManager is not connected; call connect() first.")
        return self._sessionmaker

    async def health_check(self) -> bool:
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - health probe must never raise
            _logger.warning("postgres.health_check.failed", exc_info=True)
            return False


# Process-wide singleton.
postgres_manager = PostgresManager()

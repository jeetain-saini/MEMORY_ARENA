"""PostgresManager against a file SQLite (deployment hardening, Stage 14).

Confirms the manager builds a working engine for a ``sqlite+aiosqlite`` URL
without the Postgres pool args, can create the schema, persist + read a row, and
report healthy — the free-tier database path.
"""

from __future__ import annotations

import asyncio
import pathlib
import tempfile

from sqlalchemy import select
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.postgres import PostgresManager


def _sqlite_settings(db_path: pathlib.Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        postgres_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        jwt_secret="a-sufficiently-long-secret",
    )


def test_sqlite_engine_uses_nullpool_and_works() -> None:
    async def scenario() -> None:
        tmpdir = pathlib.Path(tempfile.mkdtemp())
        settings = _sqlite_settings(tmpdir / "demo.db")
        assert settings.is_sqlite is True

        manager = PostgresManager()
        await manager.connect(settings)
        try:
            assert isinstance(manager._engine.pool, NullPool)  # no Postgres pooling

            async with manager._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with manager.sessionmaker() as session:
                session.add(UserModel(email="deploy@example.com"))
                await session.commit()

            async with manager.sessionmaker() as session:
                row = await session.scalar(select(UserModel).where(UserModel.email == "deploy@example.com"))
                assert row is not None
                assert row.tenant_id == row.id  # column default fired

            assert await manager.health_check() is True
        finally:
            await manager.disconnect()


    asyncio.run(scenario())

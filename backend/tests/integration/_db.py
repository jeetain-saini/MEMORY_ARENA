"""Shared helpers for integration tests (isolated in-memory SQLite)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.session import create_session_factory


async def make_engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


async def seed_user(engine: AsyncEngine, user_id: UUID | None = None) -> UUID:
    user_id = user_id or uuid4()
    factory = create_session_factory(engine)
    async with factory() as session:
        session.add(UserModel(id=user_id, email=f"{user_id}@example.com"))
        await session.commit()
    return user_id

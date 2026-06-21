"""Integration tests for UserRepositoryImpl + the tenant_id column default."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from app.domain.entities.user import User
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from tests.integration._db import make_engine

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def test_add_and_fetch_user_preserves_tenant() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        factory = create_session_factory(engine)
        user = User.register(email="repo@example.com", password_hash="h")
        async with SQLAlchemyUnitOfWork(factory) as uow:
            await uow.users.add(user)
            await uow.commit()
        async with SQLAlchemyUnitOfWork(factory) as uow:
            by_id = await uow.users.get_by_id(user.id)
            by_email = await uow.users.get_by_email("repo@example.com")
        assert by_id is not None and by_id.tenant_id == user.id
        assert by_email is not None and by_email.id == user.id

    _run(scenario)


def test_direct_insert_without_tenant_id_gets_default() -> None:
    # Mirrors how existing tests seed users (UserModel without tenant_id): the
    # NOT NULL column default must mirror the row id.
    async def scenario() -> None:
        engine = await make_engine()
        factory = create_session_factory(engine)
        uid = uuid4()
        async with factory() as session:
            session.add(UserModel(id=uid, email=f"{uid}@example.com"))
            await session.commit()
        async with SQLAlchemyUnitOfWork(factory) as uow:
            user = await uow.users.get_by_id(uid)
        assert user is not None
        assert user.tenant_id == uid

    _run(scenario)

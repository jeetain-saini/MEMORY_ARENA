"""Integration tests for AuthService (SQLite + real bcrypt/JWT + in-memory store).

Single-event-loop ``asyncio.run(scenario())`` pattern (matching the other DB
integration suites). Exercises registration, login, rotating refresh with reuse
detection, and logout end-to-end through a real Unit of Work.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import pytest

from app.application.dto.auth_dto import Credentials, RegisterCommand
from app.application.exceptions import AuthenticationError, EmailAlreadyRegisteredError
from app.application.services.auth.auth_service import AuthService
from app.application.services.observability.frozen_clock import FrozenClock
from app.domain.entities.user import User
from app.infrastructure.auth.refresh_store_memory import InMemoryRefreshTokenStore
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JwtTokenService
from tests.integration._db import make_engine

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _ctx() -> tuple[AuthService, FrozenClock, Callable[[], SQLAlchemyUnitOfWork]]:
    engine = await make_engine()
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    clock = FrozenClock(epoch=1_000_000.0)
    service = AuthService(
        uow_factory,
        BcryptPasswordHasher(rounds=4),
        JwtTokenService(secret="x" * 24, algorithm="HS256", access_ttl_seconds=900, clock=clock),
        InMemoryRefreshTokenStore(clock),
        clock,
        refresh_ttl_seconds=3600,
    )
    return service, clock, uow_factory


def test_register_persists_and_enables_login() -> None:
    async def scenario() -> None:
        service, _clock, _uow = await _ctx()
        identity = await service.register(RegisterCommand(email="A@Example.com", password="password123"))
        assert identity.email == "a@example.com"
        pair = await service.login(Credentials(email="a@example.com", password="password123"))
        assert pair.access_token and pair.refresh_token
        assert pair.token_type == "bearer"
        assert pair.expires_in == 900

    _run(scenario)


def test_register_duplicate_email_rejected() -> None:
    async def scenario() -> None:
        service, _clock, _uow = await _ctx()
        await service.register(RegisterCommand(email="dup@example.com", password="password123"))
        with pytest.raises(EmailAlreadyRegisteredError):
            await service.register(RegisterCommand(email="dup@example.com", password="other12345"))

    _run(scenario)


def test_login_wrong_password_and_unknown_email_fail() -> None:
    async def scenario() -> None:
        service, _clock, _uow = await _ctx()
        await service.register(RegisterCommand(email="u@example.com", password="password123"))
        with pytest.raises(AuthenticationError):
            await service.login(Credentials(email="u@example.com", password="wrong-password"))
        with pytest.raises(AuthenticationError):
            await service.login(Credentials(email="ghost@example.com", password="password123"))

    _run(scenario)


def test_login_inactive_user_fails() -> None:
    async def scenario() -> None:
        service, _clock, uow_factory = await _ctx()
        hasher = BcryptPasswordHasher(rounds=4)
        async with uow_factory() as uow:
            await uow.users.add(
                User(email="inactive@example.com", password_hash=hasher.hash("password123"), is_active=False)
            )
            await uow.commit()
        with pytest.raises(AuthenticationError):
            await service.login(Credentials(email="inactive@example.com", password="password123"))

    _run(scenario)


def test_refresh_rotates_tokens() -> None:
    async def scenario() -> None:
        service, _clock, _uow = await _ctx()
        await service.register(RegisterCommand(email="r@example.com", password="password123"))
        pair1 = await service.login(Credentials(email="r@example.com", password="password123"))
        pair2 = await service.refresh(pair1.refresh_token)
        assert pair2.refresh_token != pair1.refresh_token
        assert pair2.access_token  # new access issued
        # The new refresh token works.
        pair3 = await service.refresh(pair2.refresh_token)
        assert pair3.refresh_token != pair2.refresh_token

    _run(scenario)


def test_refresh_reuse_detection_revokes_family() -> None:
    async def scenario() -> None:
        service, _clock, _uow = await _ctx()
        await service.register(RegisterCommand(email="reuse@example.com", password="password123"))
        pair1 = await service.login(Credentials(email="reuse@example.com", password="password123"))
        pair2 = await service.refresh(pair1.refresh_token)  # consumes pair1

        # Replaying the consumed pair1 token is reuse -> 401 + family revoked.
        with pytest.raises(AuthenticationError):
            await service.refresh(pair1.refresh_token)
        # The whole family is now dead, including the legitimately-rotated pair2.
        with pytest.raises(AuthenticationError):
            await service.refresh(pair2.refresh_token)

    _run(scenario)


def test_refresh_unknown_token_fails() -> None:
    async def scenario() -> None:
        service, _clock, _uow = await _ctx()
        with pytest.raises(AuthenticationError):
            await service.refresh("not-a-real-refresh-token")

    _run(scenario)


def test_logout_revokes_family() -> None:
    async def scenario() -> None:
        service, _clock, _uow = await _ctx()
        await service.register(RegisterCommand(email="out@example.com", password="password123"))
        pair = await service.login(Credentials(email="out@example.com", password="password123"))
        await service.logout(pair.refresh_token)
        with pytest.raises(AuthenticationError):
            await service.refresh(pair.refresh_token)

    _run(scenario)

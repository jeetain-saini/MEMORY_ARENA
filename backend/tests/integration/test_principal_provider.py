"""Tests for JwtPrincipalProvider + the get_current_principal dependency gate.

JwtPrincipalProvider is exercised against real SQLite + a real JwtTokenService
(FrozenClock); the dependency's AUTH_ENABLED gate and 401 paths are unit-tested
directly with a fake provider (no HTTP needed).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import TypeVar
from uuid import uuid4

import pytest

from app.api.v1.dependencies.providers import get_current_principal
from app.application.dto.auth_dto import AuthPrincipal
from app.application.exceptions import AuthenticationError
from app.application.interfaces.principal_provider import PrincipalProvider
from app.application.services.observability.frozen_clock import FrozenClock
from app.domain.entities.user import User
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.security.jwt_principal_provider import JwtPrincipalProvider
from app.infrastructure.security.jwt_token_service import JwtTokenService
from tests.integration._db import make_engine

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _ctx():
    engine = await make_engine()
    factory = create_session_factory(engine)
    clock = FrozenClock(epoch=1_000_000.0)
    tokens = JwtTokenService(secret="x" * 24, algorithm="HS256", access_ttl_seconds=900, clock=clock)
    provider = JwtPrincipalProvider(tokens, lambda: SQLAlchemyUnitOfWork(factory))
    return engine, factory, clock, tokens, provider


async def _add_user(factory, **kwargs) -> User:
    user = User(email=f"{uuid4()}@example.com", password_hash="h", **kwargs)
    async with SQLAlchemyUnitOfWork(factory) as uow:
        await uow.users.add(user)
        await uow.commit()
    return user


# --- JwtPrincipalProvider --------------------------------------------------

def test_valid_token_yields_principal_with_tenant() -> None:
    async def scenario() -> None:
        _engine, factory, _clock, tokens, provider = await _ctx()
        user = await _add_user(factory)
        principal = await provider.get_principal(tokens.issue_access(user.id))
        assert principal == AuthPrincipal(user_id=user.id, tenant_id=user.tenant_id)

    _run(scenario)


def test_missing_token_is_rejected() -> None:
    async def scenario() -> None:
        *_, provider = await _ctx()
        with pytest.raises(AuthenticationError):
            await provider.get_principal(None)

    _run(scenario)


def test_invalid_token_is_rejected() -> None:
    async def scenario() -> None:
        *_, provider = await _ctx()
        with pytest.raises(AuthenticationError):
            await provider.get_principal("not.a.jwt")

    _run(scenario)


def test_expired_token_is_rejected() -> None:
    async def scenario() -> None:
        _engine, factory, clock, tokens, provider = await _ctx()
        user = await _add_user(factory)
        token = tokens.issue_access(user.id)
        clock.advance(901)
        with pytest.raises(AuthenticationError):
            await provider.get_principal(token)

    _run(scenario)


def test_unknown_user_is_rejected() -> None:
    async def scenario() -> None:
        _engine, _factory, _clock, tokens, provider = await _ctx()
        with pytest.raises(AuthenticationError):
            await provider.get_principal(tokens.issue_access(uuid4()))

    _run(scenario)


def test_inactive_user_is_rejected() -> None:
    async def scenario() -> None:
        _engine, factory, _clock, tokens, provider = await _ctx()
        user = await _add_user(factory, is_active=False)
        with pytest.raises(AuthenticationError):
            await provider.get_principal(tokens.issue_access(user.id))

    _run(scenario)


# --- get_current_principal gate -------------------------------------------

class _FakeProvider(PrincipalProvider):
    def __init__(self, principal: AuthPrincipal | None = None) -> None:
        self._principal = principal
        self.called_with: object = "UNSET"

    async def get_principal(self, token):
        self.called_with = token
        if self._principal is None:
            raise AuthenticationError()
        return self._principal


def test_gate_returns_none_when_auth_disabled() -> None:
    provider = _FakeProvider()
    result = _run(
        lambda: get_current_principal(
            settings=SimpleNamespace(auth_enabled=False), credentials=None, provider=provider
        )
    )
    assert result is None
    assert provider.called_with == "UNSET"  # provider not consulted


def test_gate_rejects_missing_credentials_when_enabled() -> None:
    provider = _FakeProvider()  # raises on get_principal(None)
    with pytest.raises(AuthenticationError):
        _run(
            lambda: get_current_principal(
                settings=SimpleNamespace(auth_enabled=True), credentials=None, provider=provider
            )
        )


def test_gate_delegates_token_to_provider_when_enabled() -> None:
    principal = AuthPrincipal(user_id=uuid4(), tenant_id=uuid4())
    provider = _FakeProvider(principal)
    creds = SimpleNamespace(credentials="abc.def.ghi")
    result = _run(
        lambda: get_current_principal(
            settings=SimpleNamespace(auth_enabled=True), credentials=creds, provider=provider
        )
    )
    assert result == principal
    assert provider.called_with == "abc.def.ghi"

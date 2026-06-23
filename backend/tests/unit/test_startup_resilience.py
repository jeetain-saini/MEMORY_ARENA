"""Unit tests for startup datastore-readiness retry (production hardening)."""

from __future__ import annotations

import asyncio

import pytest

from app.core.startup import DatastoreUnavailableError, await_healthy


def _run(coro):
    return asyncio.run(coro)


def test_returns_true_immediately_when_healthy() -> None:
    calls = 0

    async def health() -> bool:
        nonlocal calls
        calls += 1
        return True

    assert _run(await_healthy("pg", health, attempts=5, base_delay=0)) is True
    assert calls == 1  # no retries needed


def test_retries_until_healthy() -> None:
    calls = 0

    async def health() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 3  # fails twice, then succeeds

    assert _run(await_healthy("pg", health, attempts=5, base_delay=0)) is True
    assert calls == 3


def test_retries_through_exceptions() -> None:
    calls = 0

    async def health() -> bool:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ConnectionError("connection refused")
        return True

    assert _run(await_healthy("pg", health, attempts=5, base_delay=0)) is True
    assert calls == 2


def test_required_raises_after_exhausting_attempts() -> None:
    async def health() -> bool:
        raise ConnectionError("unexpected connection_lost")

    with pytest.raises(DatastoreUnavailableError) as exc:
        _run(await_healthy("postgres", health, attempts=3, base_delay=0, required=True))
    assert "postgres" in str(exc.value)
    assert "3 attempts" in str(exc.value)


def test_optional_degrades_without_raising() -> None:
    async def health() -> bool:
        return False

    assert _run(await_healthy("redis", health, attempts=3, base_delay=0, required=False)) is False


def test_backoff_is_capped() -> None:
    # max_delay caps the exponential growth; base_delay=0 keeps the test instant.
    async def health() -> bool:
        return False

    # required=False so it returns rather than raising; just exercise the path.
    assert _run(
        await_healthy("redis", health, attempts=4, base_delay=0, max_delay=0.01, required=False)
    ) is False

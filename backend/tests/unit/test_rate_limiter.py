"""Unit tests for the rate-limiter adapters (in-memory + no-op) and factory."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from app.application.services.observability.frozen_clock import FrozenClock  # noqa: E402
from app.infrastructure.ratelimit.in_memory_limiter import InMemoryRateLimiter  # noqa: E402
from app.infrastructure.ratelimit.noop_limiter import NoOpRateLimiter  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def test_in_memory_allows_under_limit_then_blocks() -> None:
    clock = FrozenClock(epoch=1000.0)
    limiter = InMemoryRateLimiter(clock)
    d1 = _run(limiter.hit("k", limit=2, window_seconds=60))
    d2 = _run(limiter.hit("k", limit=2, window_seconds=60))
    d3 = _run(limiter.hit("k", limit=2, window_seconds=60))
    assert (d1.allowed, d1.remaining) == (True, 1)
    assert (d2.allowed, d2.remaining) == (True, 0)
    assert d3.allowed is False
    assert d3.remaining == 0
    # reset_epoch is the next window boundary; retry_after counts down to it.
    assert d3.reset_epoch == 1020  # bucket floor(1000/60)=16 -> reset (16+1)*60=1020
    assert d3.retry_after_seconds == 20


def test_in_memory_window_resets_after_advance() -> None:
    clock = FrozenClock(epoch=1000.0)
    limiter = InMemoryRateLimiter(clock)
    assert _run(limiter.hit("k", limit=1, window_seconds=60)).allowed is True
    assert _run(limiter.hit("k", limit=1, window_seconds=60)).allowed is False
    clock.advance(60)  # next window bucket
    again = _run(limiter.hit("k", limit=1, window_seconds=60))
    assert again.allowed is True
    assert again.remaining == 0


def test_in_memory_keys_are_independent() -> None:
    clock = FrozenClock(epoch=1000.0)
    limiter = InMemoryRateLimiter(clock)
    assert _run(limiter.hit("a", limit=1, window_seconds=60)).allowed is True
    assert _run(limiter.hit("b", limit=1, window_seconds=60)).allowed is True
    assert _run(limiter.hit("a", limit=1, window_seconds=60)).allowed is False


def test_noop_always_allows() -> None:
    limiter = NoOpRateLimiter()
    for _ in range(100):
        d = _run(limiter.hit("k", limit=1, window_seconds=60))
        assert d.allowed is True
        assert d.remaining == 1


def test_factory_returns_noop_when_disabled() -> None:
    from app.core.config import get_settings
    from app.infrastructure.ratelimit.factory import build_rate_limiter

    get_settings.cache_clear()
    try:
        limiter = build_rate_limiter(FrozenClock())
        assert isinstance(limiter, NoOpRateLimiter)
    finally:
        get_settings.cache_clear()

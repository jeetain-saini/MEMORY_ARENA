"""Unit tests for the cache providers (in-memory + no-op) and factory."""

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
from app.infrastructure.cache.in_memory_cache import InMemoryCacheProvider  # noqa: E402
from app.infrastructure.cache.noop_cache import NoOpCacheProvider  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def test_set_get_roundtrip() -> None:
    cache = InMemoryCacheProvider(FrozenClock(epoch=1000.0))
    _run(cache.set("k", "v", ttl_seconds=60))
    assert _run(cache.get("k")) == "v"
    assert _run(cache.get("missing")) is None


def test_ttl_expiry_via_clock() -> None:
    clock = FrozenClock(epoch=1000.0)
    cache = InMemoryCacheProvider(clock)
    _run(cache.set("k", "v", ttl_seconds=30))
    clock.advance(29)
    assert _run(cache.get("k")) == "v"
    clock.advance(1)  # now == expiry -> expired (>=)
    assert _run(cache.get("k")) is None


def test_delete() -> None:
    cache = InMemoryCacheProvider(FrozenClock(epoch=1000.0))
    _run(cache.set("k", "v", ttl_seconds=60))
    _run(cache.delete("k"))
    assert _run(cache.get("k")) is None
    _run(cache.delete("absent"))  # no error


def test_delete_prefix() -> None:
    cache = InMemoryCacheProvider(FrozenClock(epoch=1000.0))
    _run(cache.set("analytics:user:1", "a", ttl_seconds=60))
    _run(cache.set("analytics:global", "g", ttl_seconds=60))
    _run(cache.set("health:user:1", "h", ttl_seconds=60))
    _run(cache.delete_prefix("analytics:"))
    assert _run(cache.get("analytics:user:1")) is None
    assert _run(cache.get("analytics:global")) is None
    assert _run(cache.get("health:user:1")) == "h"


def test_noop_is_inert() -> None:
    cache = NoOpCacheProvider()
    _run(cache.set("k", "v", ttl_seconds=60))
    assert _run(cache.get("k")) is None
    _run(cache.delete("k"))
    _run(cache.delete_prefix("x"))


def test_factory_default_is_noop() -> None:
    from app.core.config import get_settings
    from app.infrastructure.cache.factory import build_cache_provider

    get_settings.cache_clear()
    build_cache_provider.cache_clear()
    try:
        assert isinstance(build_cache_provider(), NoOpCacheProvider)
    finally:
        get_settings.cache_clear()
        build_cache_provider.cache_clear()


def test_factory_memory_selection() -> None:
    from app.core.config import get_settings
    from app.infrastructure.cache.factory import build_cache_provider

    os.environ["CACHE_BACKEND"] = "memory"
    get_settings.cache_clear()
    build_cache_provider.cache_clear()
    try:
        assert isinstance(build_cache_provider(), InMemoryCacheProvider)
    finally:
        os.environ.pop("CACHE_BACKEND", None)
        get_settings.cache_clear()
        build_cache_provider.cache_clear()

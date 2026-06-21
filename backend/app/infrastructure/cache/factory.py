"""Cache-provider factory — config-driven, process-wide singleton (Phase 5).

``noop`` (default) | ``memory`` | ``redis`` via ``CACHE_BACKEND``. Cached as a
singleton so the request services and the invalidation event handler share the
*same* instance (essential for the in-memory backend). The in-memory adapter
uses a real ``MonotonicClock`` for TTL; tests override the provider with a
``FrozenClock``-backed instance for determinism. Call
``build_cache_provider.cache_clear()`` in tests that change configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.cache_provider import CacheProvider
from app.core.config import get_settings
from app.infrastructure.cache.in_memory_cache import InMemoryCacheProvider
from app.infrastructure.cache.noop_cache import NoOpCacheProvider
from app.infrastructure.observability.monotonic_clock import MonotonicClock


@lru_cache(maxsize=1)
def build_cache_provider() -> CacheProvider:
    backend = get_settings().cache_backend.lower()
    if backend == "memory":
        return InMemoryCacheProvider(MonotonicClock())
    if backend == "redis":
        from app.infrastructure.cache.redis import redis_manager
        from app.infrastructure.cache.redis_cache import RedisCacheProvider

        return RedisCacheProvider(redis_manager.client)
    return NoOpCacheProvider()

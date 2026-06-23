"""Distributed-lock factory — config-driven selection (Stage 18.3).

``InMemoryDistributedLock`` by default (offline/single-process, no Redis needed);
the cross-instance ``RedisDistributedLock`` when ``LOCK_BACKEND=redis``. Mirrors
the cache / rate-limit / refresh-store factories: the Redis import is lazy so the
offline default never touches the Redis client.
"""

from __future__ import annotations

from app.application.interfaces.clock import Clock
from app.application.interfaces.distributed_lock import DistributedLock
from app.core.config import get_settings
from app.infrastructure.locks.in_memory_lock import InMemoryDistributedLock


def build_distributed_lock(clock: Clock) -> DistributedLock:
    settings = get_settings()
    if settings.lock_backend == "redis":
        from app.infrastructure.cache.redis import redis_manager
        from app.infrastructure.locks.redis_lock import RedisDistributedLock

        return RedisDistributedLock(redis_manager.client)
    return InMemoryDistributedLock(clock)

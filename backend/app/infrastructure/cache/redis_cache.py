"""RedisCacheProvider — durable, multi-instance cache (fail-open).

Production adapter (selected when ``CACHE_BACKEND=redis``). Keys are namespaced
under ``cache:`` to keep them distinct from other Redis users (rate limits,
refresh tokens). Every operation **fails open**: any Redis error is logged and
swallowed so a cache outage degrades to a miss/recompute rather than an error —
correctness is never sacrificed for cache availability.

Not exercised by the offline suite (no Redis server); verified against live
Redis. Contract parity is guaranteed by the in-memory adapter's tests.
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis

from app.application.interfaces.cache_provider import CacheProvider

_logger = logging.getLogger("memoryarena.cache")
_NS = "cache:"


class RedisCacheProvider(CacheProvider):
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(_NS + key)
        except Exception as exc:  # noqa: BLE001 — fail open: treat as a miss
            _logger.warning("cache.get_failed", extra={"key": key, "error": str(exc)})
            return None

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        try:
            await self._client.set(_NS + key, value, ex=max(1, ttl_seconds))
        except Exception as exc:  # noqa: BLE001 — fail open
            _logger.warning("cache.set_failed", extra={"key": key, "error": str(exc)})

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(_NS + key)
        except Exception as exc:  # noqa: BLE001 — fail open
            _logger.warning("cache.delete_failed", extra={"key": key, "error": str(exc)})

    async def delete_prefix(self, prefix: str) -> None:
        try:
            async for key in self._client.scan_iter(match=f"{_NS}{prefix}*"):
                await self._client.delete(key)
        except Exception as exc:  # noqa: BLE001 — fail open
            _logger.warning("cache.delete_prefix_failed", extra={"prefix": prefix, "error": str(exc)})

"""Redis connection manager (async client + connection pool).

A single client backed by a connection pool is shared process-wide. Created at
startup, closed at shutdown. Stage 1 only establishes connectivity and a health
probe; cache abstractions and queues come later.
"""

from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis

from app.core.config import Settings

_logger = logging.getLogger("memoryarena.redis")


class RedisManager:
    """Lifecycle owner for the async Redis client."""

    def __init__(self) -> None:
        self._client: Redis | None = None
        self._health_timeout: float = 5.0

    async def connect(self, settings: Settings) -> None:
        if self._client is not None:
            return
        self._health_timeout = settings.health_check_timeout
        self._client = Redis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=True,
            health_check_interval=30,
            # Fast-failure: bound socket connect + command so a dead Redis fails
            # in seconds instead of hanging the caller.
            socket_connect_timeout=settings.redis_socket_timeout,
            socket_timeout=settings.redis_socket_timeout,
        )
        _logger.info("redis.connected")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            _logger.info("redis.disconnected")

    @property
    def client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("RedisManager is not connected; call connect() first.")
        return self._client

    async def health_check(self) -> bool:
        if self._client is None:
            return False
        try:
            async with asyncio.timeout(self._health_timeout):
                return bool(await self._client.ping())
        except (Exception, asyncio.TimeoutError):  # noqa: BLE001 - probe never raises
            _logger.warning("redis.health_check.failed", exc_info=True)
            return False


# Process-wide singleton.
redis_manager = RedisManager()

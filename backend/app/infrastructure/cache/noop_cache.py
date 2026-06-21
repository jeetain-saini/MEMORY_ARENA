"""NoOpCacheProvider — caches nothing (the default).

Cache-aside reduces to "always recompute", so behavior is identical to having no
cache at all.
"""

from __future__ import annotations

from app.application.interfaces.cache_provider import CacheProvider


class NoOpCacheProvider(CacheProvider):
    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def delete_prefix(self, prefix: str) -> None:
        return None

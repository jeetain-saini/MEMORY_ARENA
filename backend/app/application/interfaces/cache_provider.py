"""CacheProvider port — a string key/value cache with TTL.

The cache stores opaque serialized strings; *what* to cache, *how* to key it, and
*how* to (de)serialize are application concerns (cache-aside lives in the
services), so the adapters stay pure I/O with no business logic. Production
adapters must **fail open** — a cache outage degrades to a miss/recompute, never
an error.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class CacheProvider(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Return the cached value, or None on miss (or any backend error)."""

    @abstractmethod
    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        """Store ``value`` under ``key`` with a time-to-live."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove a key (no-op if absent)."""

    @abstractmethod
    async def delete_prefix(self, prefix: str) -> None:
        """Remove all keys starting with ``prefix`` (namespace invalidation)."""

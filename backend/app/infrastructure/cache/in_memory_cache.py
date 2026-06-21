"""InMemoryCacheProvider — process-local cache with clock-based TTL.

The offline/test + single-instance adapter. Expiry is evaluated against the
injected ``Clock`` (``now_epoch``), so TTL behavior is deterministic under
``FrozenClock``. Process-local — not multi-instance safe (use Redis for that).
"""

from __future__ import annotations

from app.application.interfaces.cache_provider import CacheProvider
from app.application.interfaces.clock import Clock


class InMemoryCacheProvider(CacheProvider):
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._store: dict[str, tuple[str, float]] = {}  # key -> (value, expires_epoch)

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self._clock.now_epoch() >= expires_at:
            self._store.pop(key, None)  # lazy eviction
            return None
        return value

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self._store[key] = (value, self._clock.now_epoch() + ttl_seconds)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def delete_prefix(self, prefix: str) -> None:
        for key in [k for k in self._store if k.startswith(prefix)]:
            self._store.pop(key, None)

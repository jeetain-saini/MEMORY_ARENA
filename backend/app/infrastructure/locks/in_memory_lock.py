"""InMemoryDistributedLock — process-local lease (offline/dev default).

Correct for a single process: asyncio is single-threaded, so each method runs to
completion with no interleaving between its read and write. Expiry is evaluated
against the injected :class:`Clock` (``now_epoch``), so a ``FrozenClock`` makes
lease expiry deterministic in tests. It does *not* coordinate across processes —
that is the Redis adapter's job — but it gives the same token/renew/release
contract so services behave identically regardless of which is wired in.
"""

from __future__ import annotations

from uuid import uuid4

from app.application.interfaces.clock import Clock
from app.application.interfaces.distributed_lock import DistributedLock


class InMemoryDistributedLock(DistributedLock):
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._held: dict[str, tuple[str, float]] = {}  # key -> (token, expires_epoch)

    def _live_owner(self, key: str, now: float) -> str | None:
        entry = self._held.get(key)
        if entry is None or entry[1] <= now:
            return None
        return entry[0]

    async def acquire(self, key: str, *, ttl_seconds: int) -> str | None:
        now = self._clock.now_epoch()
        if self._live_owner(key, now) is not None:
            return None
        token = uuid4().hex
        self._held[key] = (token, now + ttl_seconds)
        return token

    async def renew(self, key: str, token: str, *, ttl_seconds: int) -> bool:
        now = self._clock.now_epoch()
        if self._live_owner(key, now) != token:
            return False
        self._held[key] = (token, now + ttl_seconds)
        return True

    async def release(self, key: str, token: str) -> bool:
        entry = self._held.get(key)
        if entry is not None and entry[0] == token:
            del self._held[key]
            return True
        return False

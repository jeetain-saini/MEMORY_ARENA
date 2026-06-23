"""single_owner — an async context manager over the DistributedLock port.

Wraps acquire / renew / release into the idiomatic ``async with`` shape used by
single-owner maintenance jobs::

    async with single_owner(lock, "intelligence:maintenance", ttl_seconds=300) as lease:
        if lease is None:
            return  # another instance owns the cycle this tick
        for tenant in tenants:
            ...work...
            await lease.renew()  # keep the lease alive across a long cycle

The lease is released on exit (including on error). ``lease is None`` means the
lock was not acquired — the caller should skip, not block.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.application.interfaces.distributed_lock import DistributedLock


@dataclass
class LockLease:
    """A held lease; renew to extend it, release to free it early."""

    key: str
    token: str
    ttl_seconds: int
    _lock: DistributedLock

    async def renew(self) -> bool:
        """Extend the lease. Returns False if ownership was lost (let the caller stop)."""
        return await self._lock.renew(self.key, self.token, ttl_seconds=self.ttl_seconds)

    async def release(self) -> bool:
        return await self._lock.release(self.key, self.token)


@asynccontextmanager
async def single_owner(
    lock: DistributedLock, key: str, *, ttl_seconds: int
) -> AsyncIterator[LockLease | None]:
    token = await lock.acquire(key, ttl_seconds=ttl_seconds)
    if token is None:
        yield None
        return
    lease = LockLease(key=key, token=token, ttl_seconds=ttl_seconds, _lock=lock)
    try:
        yield lease
    finally:
        await lease.release()

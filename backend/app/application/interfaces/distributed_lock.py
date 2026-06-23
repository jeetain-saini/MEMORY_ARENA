"""DistributedLock port — single-owner coordination across instances (Stage 18.3).

When MemoryArena runs as more than one process (multiple API replicas, or a
dedicated worker beside the API), the periodic maintenance cycle must run on
exactly *one* owner at a time — otherwise two instances evolve / promote /
cluster / forget the same tenant concurrently and race on the same rows and
graph edges. This port expresses a mutual-exclusion lease with a TTL:

  * ``acquire`` returns an opaque ownership *token* if the lock was free, else
    ``None`` (someone else owns it, or — for fail-closed backends — the lock
    store is unreachable and we decline rather than risk a double run);
  * ``renew`` extends the lease *iff* the caller still owns it (token match),
    so a long cycle keeps the lock alive instead of letting the TTL lapse;
  * ``release`` frees the lock *iff* the caller still owns it (compare-and-del),
    so a slow owner whose lease already expired cannot delete a lock another
    instance has since acquired.

The TTL is the safety net: if an owner crashes mid-cycle the lease expires on
its own and another instance can take over, so a dead owner never deadlocks the
system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class DistributedLock(ABC):
    @abstractmethod
    async def acquire(self, key: str, *, ttl_seconds: int) -> str | None:
        """Try to take ``key`` for ``ttl_seconds``; return an ownership token or None."""

    @abstractmethod
    async def renew(self, key: str, token: str, *, ttl_seconds: int) -> bool:
        """Extend the lease on ``key`` iff ``token`` still owns it. Return success."""

    @abstractmethod
    async def release(self, key: str, token: str) -> bool:
        """Release ``key`` iff ``token`` still owns it (compare-and-delete)."""

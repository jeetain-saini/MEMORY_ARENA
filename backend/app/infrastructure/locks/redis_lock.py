"""RedisDistributedLock — cross-instance lease on Redis (production adapter).

Selected when ``LOCK_BACKEND=redis``. Uses the canonical single-key lease:

  * ``acquire`` = ``SET key token NX PX ttl`` — atomic take-if-free with expiry;
  * ``renew``   = a Lua compare-and-``PEXPIRE`` (extend only if we still own it);
  * ``release`` = a Lua compare-and-``DEL`` (free only if we still own it),

so a slow owner whose lease already lapsed can never renew or delete a lock that
another instance has since taken. Keys are namespaced under ``lock:`` to stay
distinct from cache / rate-limit / refresh keys on a shared Redis.

Fails **closed**: if Redis is unreachable, ``acquire`` returns ``None`` (decline
the work) rather than risk two owners running at once — the opposite of the
cache's fail-open stance, because here correctness depends on exclusivity.
Verified against live Redis (mirroring the other Redis adapters); the in-memory
adapter guarantees contract parity for the offline suite.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from redis.asyncio import Redis

from app.application.interfaces.distributed_lock import DistributedLock

_logger = logging.getLogger("memoryarena.locks")
_NS = "lock:"

# KEYS[1] = lock key; ARGV[1] = token; ARGV[2] = ttl_ms. Return 1 on success.
_RENEW_LUA = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('PEXPIRE', KEYS[1], ARGV[2]) else return 0 end"
)
_RELEASE_LUA = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL', KEYS[1]) else return 0 end"
)


class RedisDistributedLock(DistributedLock):
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def acquire(self, key: str, *, ttl_seconds: int) -> str | None:
        token = uuid4().hex
        try:
            ok = await self._client.set(
                _NS + key, token, nx=True, px=max(1, ttl_seconds) * 1000
            )
        except Exception as exc:  # noqa: BLE001 — fail closed: decline rather than double-run
            _logger.warning("lock.acquire_failed", extra={"key": key, "error": str(exc)})
            return None
        return token if ok else None

    async def renew(self, key: str, token: str, *, ttl_seconds: int) -> bool:
        try:
            res = await self._client.eval(
                _RENEW_LUA, 1, _NS + key, token, max(1, ttl_seconds) * 1000
            )
        except Exception as exc:  # noqa: BLE001 — treat as lost lease
            _logger.warning("lock.renew_failed", extra={"key": key, "error": str(exc)})
            return False
        return bool(res)

    async def release(self, key: str, token: str) -> bool:
        try:
            res = await self._client.eval(_RELEASE_LUA, 1, _NS + key, token)
        except Exception as exc:  # noqa: BLE001 — lease will expire on its own
            _logger.warning("lock.release_failed", extra={"key": key, "error": str(exc)})
            return False
        return bool(res)

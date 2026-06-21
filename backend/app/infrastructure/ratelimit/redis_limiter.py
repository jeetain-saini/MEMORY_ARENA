"""RedisRateLimiter — durable, multi-instance fixed-window counter.

The production adapter (selected when ``RATE_LIMIT_ENABLED`` is true). Each
window is a key ``ratelimit:{key}:{bucket}``; one atomic Lua script does
``INCR`` and, on the first hit only, ``EXPIRE(window + 1)`` (the +1 second of
slack avoids a key expiring a hair before its window boundary). TTL self-cleans
— no scans, no cleanup jobs, no persistence. Multi-instance safe via shared
Redis.

Not exercised by the offline suite (no Redis server); a fakeredis-guarded test
covers it when available, and behavioral parity with the in-memory adapter is
guaranteed by the shared window math + the ``RateLimitDecision`` contract.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.application.dto.ratelimit_dto import RateLimitDecision
from app.application.interfaces.clock import Clock
from app.application.interfaces.rate_limiter import RateLimiter
from app.infrastructure.ratelimit.window import build_decision, current_bucket

# KEYS[1] = window key; ARGV[1] = ttl seconds. Returns the post-increment count.
_HIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RedisRateLimiter(RateLimiter):
    def __init__(self, client: Redis, clock: Clock) -> None:
        self._client = client
        self._clock = clock
        self._hit = client.register_script(_HIT_LUA)

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = self._clock.now_epoch()
        bucket = current_bucket(now, window_seconds)
        redis_key = f"ratelimit:{key}:{bucket}"
        count = int(await self._hit(keys=[redis_key], args=[window_seconds + 1]))
        return build_decision(count=count, limit=limit, now_epoch=now, window_seconds=window_seconds)

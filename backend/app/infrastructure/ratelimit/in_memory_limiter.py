"""InMemoryRateLimiter — deterministic, process-local fixed-window counter.

The tests/dev adapter (single instance only). Counts per ``key`` within the
current window bucket derived from the injected ``Clock``; a new bucket resets
the count. Deterministic under ``FrozenClock``.
"""

from __future__ import annotations

from app.application.dto.ratelimit_dto import RateLimitDecision
from app.application.interfaces.clock import Clock
from app.application.interfaces.rate_limiter import RateLimiter
from app.infrastructure.ratelimit.window import build_decision, current_bucket


class InMemoryRateLimiter(RateLimiter):
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._counters: dict[str, tuple[int, int]] = {}  # key -> (bucket, count)

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = self._clock.now_epoch()
        bucket = current_bucket(now, window_seconds)
        existing = self._counters.get(key)
        count = existing[1] + 1 if existing is not None and existing[0] == bucket else 1
        self._counters[key] = (bucket, count)
        return build_decision(count=count, limit=limit, now_epoch=now, window_seconds=window_seconds)

"""Rate-limiter factory — config-driven selection (Stage 14 Phase 4).

``NoOpRateLimiter`` when ``RATE_LIMIT_ENABLED`` is false (the default, so no Redis
is needed at rest); the durable ``RedisRateLimiter`` when enabled. The in-memory
adapter is wired by tests via a provider override (the established offline
pattern). The clock is injected so window math is deterministic in tests.
"""

from __future__ import annotations

from app.application.interfaces.clock import Clock
from app.application.interfaces.rate_limiter import RateLimiter
from app.core.config import get_settings
from app.infrastructure.ratelimit.noop_limiter import NoOpRateLimiter


def build_rate_limiter(clock: Clock) -> RateLimiter:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return NoOpRateLimiter()
    from app.infrastructure.cache.redis import redis_manager
    from app.infrastructure.ratelimit.redis_limiter import RedisRateLimiter

    return RedisRateLimiter(redis_manager.client, clock)

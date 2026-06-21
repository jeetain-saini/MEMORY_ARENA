"""NoOpRateLimiter — always allows.

The default when ``RATE_LIMIT_ENABLED`` is false, so the app imposes no limits
and needs no Redis. ``remaining`` is reported as the full limit.
"""

from __future__ import annotations

from app.application.dto.ratelimit_dto import RateLimitDecision
from app.application.interfaces.rate_limiter import RateLimiter


class NoOpRateLimiter(RateLimiter):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        return RateLimitDecision(
            allowed=True, limit=limit, remaining=limit, retry_after_seconds=0, reset_epoch=0
        )

"""Rate-limit enforcement dependency (Stage 14 Phase 4).

A single router-level dependency wired onto the aggregate v1 router, so every
endpoint is covered uniformly with exemptions handled in one place. It:

* early-returns when ``RATE_LIMIT_ENABLED`` is false or the path is exempt,
* resolves the identity (authenticated user > trusted forwarded IP > client IP),
  **never raising** — rate limiting must not produce 401s,
* applies the path's tier policy, counts the hit via the ``RateLimiter`` port,
* sets ``X-RateLimit-*`` headers on success, and raises ``RateLimitExceeded``
  (-> 429 + ``Retry-After``) when the window is exhausted.

Identity decoding uses the ``TokenService`` (signature/expiry only — no DB load),
so it is cheap and independent of the strict auth gate.
"""

from __future__ import annotations

from fastapi import Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.v1.dependencies.providers import get_app_settings, get_clock
from app.application.exceptions import RateLimitExceeded
from app.application.interfaces.clock import Clock
from app.application.interfaces.rate_limiter import RateLimiter
from app.application.services.ratelimit.config import RateLimitConfig
from app.application.services.ratelimit.policy import is_exempt, limit_for, resolve_policy
from app.core.config import Settings
from app.infrastructure.auth.factory import build_token_service
from app.infrastructure.ratelimit.factory import build_rate_limiter

_bearer = HTTPBearer(auto_error=False)


def get_rate_limit_config(settings: Settings = Depends(get_app_settings)) -> RateLimitConfig:
    return RateLimitConfig(
        window_seconds=settings.rate_limit_window_seconds,
        default_auth=settings.rate_limit_default_auth,
        default_anon=settings.rate_limit_default_anon,
        auth_endpoints_anon=settings.rate_limit_auth_endpoints_anon,
        query_auth=settings.rate_limit_query_auth,
        query_anon=settings.rate_limit_query_anon,
        ingest_auth=settings.rate_limit_ingest_auth,
        trust_forwarded_for=settings.rate_limit_trust_forwarded_for,
    )


def get_rate_limiter(clock: Clock = Depends(get_clock)) -> RateLimiter:
    return build_rate_limiter(clock)


def _client_ip(request: Request, config: RateLimitConfig) -> str:
    if config.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_rate_limit_identity(
    request: Request,
    config: RateLimitConfig = Depends(get_rate_limit_config),
    clock: Clock = Depends(get_clock),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    # Authenticated identity (best-effort; never raises -> never a 401).
    if credentials is not None:
        try:
            claims = build_token_service(clock).decode_access(credentials.credentials)
            return f"user:{claims.user_id}"
        except Exception:  # noqa: BLE001 — rate limiting must not surface auth errors
            pass
    return f"ip:{_client_ip(request, config)}"


async def enforce_rate_limit(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_app_settings),
    config: RateLimitConfig = Depends(get_rate_limit_config),
    limiter: RateLimiter = Depends(get_rate_limiter),
    identity: str = Depends(get_rate_limit_identity),
) -> None:
    if not settings.rate_limit_enabled:
        return
    path = request.url.path
    if is_exempt(path, config):
        return
    policy = resolve_policy(path, config)
    limit = limit_for(policy, authenticated=identity.startswith("user:"))
    decision = await limiter.hit(
        f"{policy.tier}:{identity}", limit=limit, window_seconds=policy.window_seconds
    )
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    response.headers["X-RateLimit-Reset"] = str(decision.reset_epoch)
    if not decision.allowed:
        raise RateLimitExceeded(
            retry_after_seconds=decision.retry_after_seconds, reset_epoch=decision.reset_epoch
        )

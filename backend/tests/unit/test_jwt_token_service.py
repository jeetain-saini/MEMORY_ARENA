"""Unit tests for JwtTokenService — clock-driven, deterministic expiry."""

from __future__ import annotations

from uuid import uuid4

import jwt
import pytest

from app.application.exceptions import AuthenticationError
from app.application.services.observability.frozen_clock import FrozenClock
from app.infrastructure.security.jwt_token_service import JwtTokenService

_SECRET = "x" * 24


def _service(clock: FrozenClock, *, ttl: int = 900, secret: str = _SECRET) -> JwtTokenService:
    return JwtTokenService(secret=secret, algorithm="HS256", access_ttl_seconds=ttl, clock=clock)


def test_issue_and_decode_roundtrip() -> None:
    clock = FrozenClock(epoch=1000.0)
    svc = _service(clock)
    uid = uuid4()
    token = svc.issue_access(uid)
    claims = svc.decode_access(token)
    assert claims.user_id == uid
    assert claims.issued_at == 1000
    assert claims.expires_at == 1900


def test_claims_are_minimal() -> None:
    clock = FrozenClock(epoch=1000.0)
    token = _service(clock).issue_access(uuid4())
    # Inspect claim structure only; the FrozenClock epoch is in the past relative
    # to real wall-clock time, so skip PyJWT's own exp check here.
    payload = jwt.decode(token, _SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert set(payload) == {"sub", "typ", "iat", "exp"}
    assert payload["typ"] == "access"


def test_token_expires_after_clock_advances_past_exp() -> None:
    clock = FrozenClock(epoch=1000.0)
    svc = _service(clock, ttl=900)
    token = svc.issue_access(uuid4())
    clock.advance(900)  # now == exp -> expired (>= comparison)
    with pytest.raises(AuthenticationError):
        svc.decode_access(token)


def test_token_valid_just_before_expiry() -> None:
    clock = FrozenClock(epoch=1000.0)
    svc = _service(clock, ttl=900)
    token = svc.issue_access(uuid4())
    clock.advance(899)
    assert svc.decode_access(token).expires_at == 1900


def test_tampered_token_rejected() -> None:
    clock = FrozenClock(epoch=1000.0)
    svc = _service(clock)
    token = svc.issue_access(uuid4())
    with pytest.raises(AuthenticationError):
        svc.decode_access(token + "tamper")


def test_wrong_secret_rejected() -> None:
    clock = FrozenClock(epoch=1000.0)
    token = _service(clock).issue_access(uuid4())
    with pytest.raises(AuthenticationError):
        _service(clock, secret="d" * 24).decode_access(token)


def test_wrong_token_type_rejected() -> None:
    clock = FrozenClock(epoch=1000.0)
    svc = _service(clock)
    forged = jwt.encode(
        {"sub": str(uuid4()), "typ": "refresh", "iat": 1000, "exp": 9999}, _SECRET, algorithm="HS256"
    )
    with pytest.raises(AuthenticationError):
        svc.decode_access(forged)

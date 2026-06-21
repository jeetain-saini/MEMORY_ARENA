"""JwtTokenService — the production TokenService adapter (PyJWT).

Issues minimal access tokens (``sub``/``typ``/``iat``/``exp``) and verifies them.
All time comes from the injected ``Clock.now_epoch()`` — PyJWT's own ``exp``/
``iat`` checks are disabled and expiry is evaluated against the clock — so token
lifetimes are fully deterministic under a ``FrozenClock`` in tests.
"""

from __future__ import annotations

from uuid import UUID

import jwt

from app.application.dto.auth_dto import AccessClaims
from app.application.exceptions import AuthenticationError
from app.application.interfaces.clock import Clock
from app.application.interfaces.token_service import TokenService

_ACCESS_TYP = "access"


class JwtTokenService(TokenService):
    def __init__(
        self,
        *,
        secret: str,
        algorithm: str,
        access_ttl_seconds: int,
        clock: Clock,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._ttl = access_ttl_seconds
        self._clock = clock

    @property
    def access_ttl_seconds(self) -> int:
        return self._ttl

    def issue_access(self, user_id: UUID) -> str:
        issued = int(self._clock.now_epoch())
        payload = {
            "sub": str(user_id),
            "typ": _ACCESS_TYP,
            "iat": issued,
            "exp": issued + self._ttl,
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode_access(self, token: str) -> AccessClaims:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                # The injected clock is the single source of time, so disable
                # PyJWT's wall-clock based temporal validation.
                options={"verify_exp": False, "verify_iat": False, "verify_nbf": False},
            )
        except jwt.InvalidTokenError as exc:  # signature/format failures
            raise AuthenticationError("Invalid access token") from exc

        if claims.get("typ") != _ACCESS_TYP:
            raise AuthenticationError("Wrong token type")
        try:
            user_id = UUID(str(claims["sub"]))
            expires_at = int(claims["exp"])
            issued_at = int(claims.get("iat", 0))
        except (KeyError, ValueError, TypeError) as exc:
            raise AuthenticationError("Malformed access token") from exc

        if self._clock.now_epoch() >= expires_at:
            raise AuthenticationError("Access token expired")
        return AccessClaims(user_id=user_id, issued_at=issued_at, expires_at=expires_at)

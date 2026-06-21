"""TokenService port — stateless access-token issuance/verification.

Issues and verifies short-lived JWT access tokens. Refresh tokens are *not* JWTs
(they are opaque and tracked by the RefreshTokenStore), so this port covers
access tokens only. All time math goes through the injected Clock's
``now_epoch()`` so expiry is deterministic in tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.auth_dto import AccessClaims


class TokenService(ABC):
    @abstractmethod
    def issue_access(self, user_id: UUID) -> str:
        """Return a signed access token for ``user_id`` (claims: sub/typ/iat/exp)."""

    @abstractmethod
    def decode_access(self, token: str) -> AccessClaims:
        """Verify signature + type + expiry and return the claims.

        Raises ``AuthenticationError`` on a missing/invalid/expired/wrong-type token.
        """

    @property
    @abstractmethod
    def access_ttl_seconds(self) -> int:
        """The access-token lifetime in seconds (for ``TokenPair.expires_in``)."""

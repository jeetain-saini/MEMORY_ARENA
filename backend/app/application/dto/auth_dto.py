"""Authentication DTOs (Stage 14 Phase 2).

Plain, framework-free dataclasses for the auth flow: registration/login inputs,
the issued token pair, decoded access claims, and the refresh-token bookkeeping
record + the result of the atomic rotation contract. No pydantic, no JWT, no
storage detail leaks here — adapters map to/from these.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from app.domain.value_objects.role import Role


@dataclass(frozen=True)
class RegisterCommand:
    email: str
    password: str
    display_name: str | None = None


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


@dataclass(frozen=True)
class AuthIdentity:
    """The public identity of an account (no credentials)."""

    user_id: UUID
    email: str


@dataclass(frozen=True)
class AuthPrincipal:
    """The authenticated caller for a request (Stage 14 Phase 3).

    Resolved from the access token + user record by a ``PrincipalProvider``.
    Authorization is performed against this in the application layer. ``None``
    (no principal) means auth is disabled and checks are skipped.
    """

    user_id: UUID
    tenant_id: UUID
    # RBAC role (Stage 19.1). Sourced from the user record on each request, so a
    # role change takes effect immediately. Defaults to USER for least privilege.
    role: Role = Role.USER

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int            # access-token lifetime in seconds
    token_type: str = "bearer"


@dataclass(frozen=True)
class AccessClaims:
    """Minimal access-token claims (Phase 2: no role/tenant)."""

    user_id: UUID
    issued_at: int             # epoch seconds
    expires_at: int            # epoch seconds


@dataclass(frozen=True)
class RefreshRecord:
    """Server-side bookkeeping for one opaque refresh token.

    ``token_id`` is the SHA-256 of the opaque token (the raw token is never
    stored). A ``family_id`` groups the rotation chain of one login session so a
    detected reuse can revoke the whole family.
    """

    token_id: str
    family_id: str
    user_id: UUID
    expires_at: float          # epoch seconds
    status: str = "active"     # "active" | "rotated"


class RotationState(str, Enum):
    """Outcome of an atomic refresh-token rotation attempt."""

    VALID = "valid"            # token consumed; a new one may be issued
    ROTATED = "rotated"        # already used -> reuse/replay detected
    REVOKED = "revoked"        # token's family was revoked
    EXPIRED = "expired"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class RotationOutcome:
    state: RotationState
    user_id: UUID | None = None
    family_id: str | None = None

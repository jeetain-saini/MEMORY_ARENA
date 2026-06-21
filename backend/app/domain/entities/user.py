"""User — an account that owns memories and authenticates.

Pure-Python identity entity. Stage 14 Phase 2 keeps it minimal: identity
(``id``/``email``), an optional display name, the credential (``password_hash``),
and an ``is_active`` flag. Authorization fields (role, tenant_id) are Phase 3.

A user with ``password_hash is None`` has no usable credential (e.g. a record
seeded before authentication existed) and cannot authenticate — login simply
fails the password check.

Stdlib only; no persistence, no frameworks, and (unlike ``Memory``) no events —
the auth flow is request/response, not event-sourced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.exceptions.errors import DomainError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class User:
    email: str
    id: UUID = field(default_factory=uuid4)
    display_name: str | None = None
    password_hash: str | None = None
    is_active: bool = True
    # Tenant the account belongs to (Stage 14 Phase 3). Each user is initially
    # their own tenant: when unset it defaults to the user's own id, so the
    # invariant "every user has a non-null tenant_id" holds after construction
    # (including rehydration from the database via the mapper).
    tenant_id: UUID | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.email or not self.email.strip():
            raise DomainError("User email must not be empty.")
        if self.tenant_id is None:
            self.tenant_id = self.id

    @classmethod
    def register(
        cls, *, email: str, password_hash: str, display_name: str | None = None
    ) -> "User":
        """Create a new, active account that is its own tenant."""
        return cls(
            email=email.strip().lower(),
            display_name=display_name,
            password_hash=password_hash,
        )

    @property
    def can_authenticate(self) -> bool:
        return self.is_active and bool(self.password_hash)

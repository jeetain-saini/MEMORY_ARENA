"""Role — the RBAC role of an authenticated principal (Stage 19.1).

Three roles, least-privilege by default:

* ``USER``    — the default. Operates only within its own ``user_id`` scope
  (which is also its tenant boundary today). Every existing account is a USER,
  so the default preserves all pre-19.1 behavior exactly.
* ``ADMIN``   — may operate across tenants (e.g. cross-user observability and
  maintenance overrides). The only role permitted to resolve a scope other than
  its own.
* ``SERVICE`` — a non-human internal caller (background workers, batch jobs).
  Trusted to act within an explicitly supplied scope, but never to escalate to
  ADMIN's cross-tenant reach.

Stored on the user record and carried in the access-token claims and
``AuthPrincipal`` so the authorization policy can enforce role rules without a
database read on the request path.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SERVICE = "service"

    @classmethod
    def from_str(cls, value: str | None) -> "Role":
        """Parse a role string, defaulting to ``USER`` for absent/unknown values.

        Tolerant by design: tokens and rows minted before 19.1 carry no role, and
        they must resolve to the least-privileged USER rather than fail.
        """
        if not value:
            return cls.USER
        try:
            return cls(value.lower())
        except ValueError:
            return cls.USER

    @property
    def is_admin(self) -> bool:
        return self is Role.ADMIN

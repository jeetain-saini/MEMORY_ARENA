"""Authorization policy (Stage 14 Phase 3) — pure, framework-free.

A single place where the user-scope and ownership rules live, so every service
enforces them identically. All functions are no-ops when ``principal is None``
(auth disabled) — preserving existing behavior exactly.

Rules (when a principal is present):

* ``resolve_scope`` — a request may only operate within its own ``user_id``. A
  missing requested scope resolves to the principal's; a *different* explicit
  scope is a cross-user attempt -> ``AuthorizationError`` (403).
* ``authorize_owner`` — a by-id resource may only be touched by its owner;
  otherwise raise ``ResourceNotFoundForCaller`` (404, to avoid leaking that the
  resource exists).

Tenancy: memories are ``user_id``-scoped and each user is their own tenant, so
user-scope enforcement *is* the tenant boundary today; ``principal.tenant_id`` is
carried for the future organization model without changing behavior now.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.auth_dto import AuthPrincipal
from app.application.exceptions import AuthorizationError, ResourceNotFoundForCaller


def resolve_scope(principal: AuthPrincipal | None, requested_user_id: UUID | None) -> UUID | None:
    """Return the authorized ``user_id`` to scope an operation to.

    * No principal (auth disabled): pass the requested scope through unchanged.
    * Principal + no explicit scope: the principal's own ``user_id``.
    * Principal + matching scope: that ``user_id``.
    * Principal + different explicit scope: ``AuthorizationError`` (403).
    """
    if principal is None:
        return requested_user_id
    if requested_user_id is None or requested_user_id == principal.user_id:
        return principal.user_id
    raise AuthorizationError("Not permitted to access another user's resources")


def authorize_owner(principal: AuthPrincipal | None, owner_id: UUID) -> None:
    """Ensure the caller owns a by-id resource (404 to callers who do not)."""
    if principal is None:
        return
    if owner_id != principal.user_id:
        raise ResourceNotFoundForCaller()

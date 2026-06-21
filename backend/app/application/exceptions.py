"""Application-layer exceptions.

Raised by use cases/services to signal outcomes the delivery layer must
translate (a missing memory, invalid input). They are framework-agnostic — no
HTTP, no FastAPI — so the application stays independent of the web layer. The
API layer maps them to HTTP responses (see app/core/exceptions.py).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


class ApplicationError(Exception):
    """Base class for application-level errors."""


class MemoryNotFoundException(ApplicationError):
    """The requested memory does not exist (or is not visible to the caller)."""

    def __init__(self, memory_id: UUID) -> None:
        self.memory_id = memory_id
        super().__init__(f"Memory {memory_id} not found")


class MemoryValidationException(ApplicationError):
    """The requested operation is invalid (e.g. nothing to update)."""

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        self.details = details
        super().__init__(message)


class AuthenticationError(ApplicationError):
    """Authentication failed (bad credentials, invalid/expired/reused token).

    Framework-free; the API layer maps it to HTTP 401 (see app/core/exceptions.py).
    The message is intentionally generic to avoid leaking which factor failed.
    """

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message)


class EmailAlreadyRegisteredError(ApplicationError):
    """Registration conflict: the email already has an account."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__("Email is already registered")


class AuthorizationError(ApplicationError):
    """The caller is authenticated but not permitted to perform the action.

    Framework-free; the API layer maps it to HTTP 403.
    """

    def __init__(self, message: str = "Operation not permitted") -> None:
        super().__init__(message)


class ResourceNotFoundForCaller(ApplicationError):
    """A by-id resource the caller may not access.

    Reported as 404 (not 403) so the API never reveals that a resource owned by
    another user exists.
    """

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message)


class RateLimitExceeded(ApplicationError):
    """The caller exceeded their rate-limit window.

    Framework-free; the API maps it to HTTP 429 with a ``Retry-After`` header.
    """

    def __init__(self, *, retry_after_seconds: int, reset_epoch: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.reset_epoch = reset_epoch
        super().__init__("Rate limit exceeded")

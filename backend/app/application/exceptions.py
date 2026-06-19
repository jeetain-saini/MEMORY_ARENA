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

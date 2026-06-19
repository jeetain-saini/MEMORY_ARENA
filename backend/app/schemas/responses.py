"""Standardized API response envelopes.

Every response the API returns — success or error — shares one shape, so
clients can parse predictably and we can evolve payloads without breaking the
contract. `success` is the discriminator; `data` carries the payload on success
and `error` carries a structured error on failure.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Machine-readable error description."""

    code: str = Field(..., description="Stable, machine-readable error code")
    message: str = Field(..., description="Human-readable explanation")
    details: Any | None = Field(default=None, description="Optional structured context")


class APIResponse(BaseModel, Generic[T]):
    """Successful response envelope."""

    success: bool = True
    data: T | None = None
    request_id: str | None = Field(default=None, description="Correlation id for tracing")


class ErrorResponse(BaseModel):
    """Failure response envelope."""

    success: bool = False
    error: ErrorDetail
    request_id: str | None = Field(default=None, description="Correlation id for tracing")

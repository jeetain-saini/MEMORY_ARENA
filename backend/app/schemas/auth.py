"""Pydantic schemas for the authentication API (Stage 14 Phase 2).

The wire contract for ``/auth/*``. Email is a plain length-bounded string (no
``EmailStr`` dependency); password has a minimum length. These map to the
framework-free auth DTOs at the edge.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.application.dto.auth_dto import (
    Credentials,
    RegisterCommand,
    TokenPair,
)


class RegisterRequestSchema(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=255)

    def to_command(self) -> RegisterCommand:
        return RegisterCommand(
            email=self.email, password=self.password, display_name=self.display_name
        )


class LoginRequestSchema(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    def to_credentials(self) -> Credentials:
        return Credentials(email=self.email, password=self.password)


class RefreshRequestSchema(BaseModel):
    refresh_token: str = Field(min_length=1)


class RegisterResponseSchema(BaseModel):
    user_id: UUID
    email: str


class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int

    @classmethod
    def from_dto(cls, dto: TokenPair) -> "TokenResponseSchema":
        return cls(
            access_token=dto.access_token,
            refresh_token=dto.refresh_token,
            token_type=dto.token_type,
            expires_in=dto.expires_in,
        )

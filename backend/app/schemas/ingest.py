"""Pydantic schemas for the ingestion endpoint (the API's wire contract)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class IngestRequestSchema(BaseModel):
    user_id: UUID
    text: str = Field(min_length=1, max_length=50_000)


class IngestAcceptedSchema(BaseModel):
    job_id: UUID
    status: str = "queued"

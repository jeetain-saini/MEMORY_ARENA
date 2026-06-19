"""SQLAlchemy declarative base, shared mixins, and the cross-dialect Vector type.

Everything ORM models share lives here:

* ``Base`` — the declarative base, with a constraint **naming convention** so
  Alembic produces stable, predictable index/constraint names.
* ``TimestampMixin`` / ``SoftDeleteMixin`` — created/updated timestamps and
  soft deletion (a ``deleted_at`` tombstone instead of a hard ``DELETE``).
* ``Vector`` — a ``TypeDecorator`` that maps to pgvector's native ``vector`` on
  PostgreSQL and degrades to a JSON-encoded ``TEXT`` elsewhere (e.g. SQLite in
  tests), so the schema is creatable on any dialect.

No engine/session lives here — see ``session.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, MetaData, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

try:  # pragma: no cover - import guard
    from pgvector.sqlalchemy import Vector as _PGVector
except ImportError:  # pragma: no cover
    _PGVector = None  # type: ignore[assignment]


# Stable names for indexes/constraints -> reproducible Alembic migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """Timezone-aware UTC now (used for Python-side column defaults)."""
    return datetime.now(timezone.utc)


# JSON on portable dialects, JSONB on PostgreSQL (indexable, binary).
JSONType = JSON().with_variant(JSONB, "postgresql")


class TimestampMixin:
    """Adds created_at / updated_at columns maintained application-side."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    """Adds a ``deleted_at`` tombstone; rows are never physically removed."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class Vector(TypeDecorator):
    """Embedding column: native pgvector on PostgreSQL, JSON TEXT elsewhere.

    Stage 3 only defines the *schema*; no embeddings are generated or searched.
    """

    impl = Text
    cache_ok = True

    def __init__(self, dim: int, **kwargs: object) -> None:
        self.dim = dim
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql" and _PGVector is not None:
            return dialect.type_descriptor(_PGVector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None or dialect.name == "postgresql":
            return value
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None or dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value

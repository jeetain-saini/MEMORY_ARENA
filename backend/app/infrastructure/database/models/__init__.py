"""ORM models - SQLAlchemy table mappings (a persistence detail).

Deliberately separate from domain/entities. Repositories translate between
them so the DB schema can change without reshaping the domain.
Stage 0: structure only - no implementation.
"""
"""Regression: pgvector numpy float32 must not leak past the persistence boundary.

On PostgreSQL the pgvector adapter returns a numpy float32 array. Before the fix,
that array flowed through cosine_similarity (sum(x*y ...)) producing numpy float32
scores that pydantic v2 cannot JSON-serialize ("Object of type float32 is not JSON
serializable" 500s). SQLite stores JSON python floats, so the offline suite never
reproduced it. These tests simulate the numpy path directly.
"""

from __future__ import annotations

import json

import pytest

from app.application.services.retrieval.scoring import cosine_similarity
from app.infrastructure.database.base import Vector

np = pytest.importorskip("numpy")


class _PgDialect:
    name = "postgresql"


class _SqliteDialect:
    name = "sqlite"


def test_vector_result_value_coerces_pgvector_float32_to_python_float() -> None:
    arr = np.array([0.1, 0.2, 0.3], dtype=np.float32)  # what pgvector returns
    out = Vector(3).process_result_value(arr, _PgDialect())
    assert all(type(x) is float for x in out)          # plain python floats
    json.dumps(out)                                     # JSON-serializable (no raise)


def test_vector_result_value_sqlite_json_path_still_works() -> None:
    out = Vector(3).process_result_value("[0.1, 0.2, 0.3]", _SqliteDialect())
    assert out == [0.1, 0.2, 0.3]
    assert all(type(x) is float for x in out)


def test_vector_result_value_none_passthrough() -> None:
    assert Vector(3).process_result_value(None, _PgDialect()) is None


def test_cosine_similarity_over_float32_returns_json_serializable_float() -> None:
    a = list(np.array([1.0, 0.0, 1.0], dtype=np.float32))  # list of np.float32
    b = list(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    score = cosine_similarity(a, b)
    assert type(score) is float          # not numpy
    json.dumps({"score": score})         # serializable
    assert 0.0 <= score <= 1.0

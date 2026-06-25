"""Integration: the inference layer prepends extraction without changing the path."""

from __future__ import annotations

import uuid

from app.application.dto.extraction_dto import ExtractionRequest
from app.application.use_cases.ingest_memory_use_cases_impl import _apply_inference


def test_prepend_rewrites_question_to_inferred_statement() -> None:
    req = ExtractionRequest(user_id=uuid.uuid4(), raw_text="What is Rust?", metadata={"source": "conversation"})
    out = _apply_inference(req)
    # Raw question never survives; inferred statement replaces it.
    assert out.raw_text == "Interested in Rust"
    assert "?" not in out.raw_text
    # Evidence travels along.
    assert out.metadata["reason_for_inference"]
    assert out.metadata["inferred_type"] == "preference"
    assert out.metadata["original_text"] == "What is Rust?"
    assert 0.0 <= out.metadata["inference_confidence"] <= 1.0
    # Existing context preserved.
    assert out.metadata["source"] == "conversation"


def test_prepend_passes_through_when_nothing_inferred() -> None:
    req = ExtractionRequest(user_id=uuid.uuid4(), raw_text="My timezone is IST", metadata={})
    out = _apply_inference(req)
    assert out is req  # unchanged object -> zero behaviour change

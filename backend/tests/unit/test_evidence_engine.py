"""Unit tests for the Phase C Evidence Engine (append-only evolution)."""

from __future__ import annotations

from app.application.services.inference.evidence import (
    Evidence,
    append_evidence,
    current_confidence,
    health,
    new_evidence,
    timeline,
)


def test_new_evidence_seeds_first_observation() -> None:
    ev = new_evidence(message="What is Rust?", confidence=0.55, importance=0.4,
                      reason="Asked about Rust.", source_type="deterministic",
                      topic="Rust", progression_stage="interest")
    assert ev["evidence_count"] == 1
    assert ev["reinforcement_count"] == 0
    assert ev["confidence_history"] == [0.55]
    assert ev["importance_history"] == [0.4]
    assert ev["first_seen"] == ev["last_seen"]
    assert ev["source_type"] == "deterministic"


def test_append_is_append_only_and_evolves_confidence() -> None:
    ev = new_evidence(message="What is Rust?", confidence=0.55, importance=0.40,
                      reason="interest", source_type="deterministic", progression_stage="interest")
    ev = append_evidence(ev, message="I'm learning Rust.", confidence=0.69, importance=0.5,
                         reason="learning", source_type="semantic", progression_stage="learning")
    ev = append_evidence(ev, message="I built a Rust API.", confidence=0.82, importance=0.7,
                         reason="uses", source_type="semantic", progression_stage="uses")
    ev = append_evidence(ev, message="Professional Rust dev.", confidence=0.94, importance=0.85,
                         reason="experienced", source_type="semantic", progression_stage="experienced")
    # History grew, nothing was overwritten.
    assert ev["confidence_history"] == [0.55, 0.69, 0.82, 0.94]
    assert ev["importance_history"] == [0.4, 0.5, 0.7, 0.85]
    assert ev["evidence_count"] == 4
    assert ev["reinforcement_count"] == 3
    assert ev["progression_history"] == ["interest", "learning", "uses", "experienced"]
    assert current_confidence(ev) == 0.94


def test_append_to_empty_creates_new() -> None:
    ev = append_evidence(None, message="I use Go.", confidence=0.8, importance=0.6,
                         reason="uses", source_type="semantic")
    assert ev["evidence_count"] == 1 and ev["confidence_history"] == [0.8]


def test_importance_evolution_independent_of_confidence() -> None:
    ev = new_evidence(message="Uses Rust", confidence=0.8, importance=0.40,
                      reason="x", source_type="semantic")
    for _ in range(9):
        ev = append_evidence(ev, message="Uses Rust again", confidence=0.8, importance=0.92,
                             reason="x", source_type="semantic")
    assert ev["importance_history"][0] == 0.4
    assert ev["importance_history"][-1] == 0.92
    assert len(ev["importance_history"]) == 10


def test_progression_history_dedupes_repeats() -> None:
    ev = new_evidence(message="m", confidence=0.7, importance=0.5, reason="x",
                      source_type="semantic", progression_stage="uses")
    ev = append_evidence(ev, message="m2", confidence=0.75, importance=0.55, reason="x",
                         source_type="semantic", progression_stage="uses")  # same stage
    assert ev["progression_history"] == ["uses"]  # not duplicated


def test_timeline_from_real_evidence() -> None:
    ev = new_evidence(message="What is Rust?", confidence=0.55, importance=0.4,
                      reason="interest", source_type="deterministic", progression_stage="interest")
    ev = append_evidence(ev, message="Uses Rust", confidence=0.82, importance=0.7,
                         reason="uses", source_type="semantic", progression_stage="uses")
    tl = timeline(ev)
    kinds = [e["event"] for e in tl]
    assert "created" in kinds and "progressed" in kinds and "reinforced" in kinds


def test_health_metrics_from_evidence() -> None:
    ev = new_evidence(message="m", confidence=0.55, importance=0.4, reason="x",
                      source_type="semantic", progression_stage="interest")
    for stage, c in [("learning", 0.69), ("uses", 0.82), ("experienced", 0.94), ("expert", 0.99)]:
        ev = append_evidence(ev, message="m", confidence=c, importance=0.9, reason="x",
                             source_type="semantic", progression_stage=stage)
    h = health(ev)
    assert h["confidence"] == 0.99
    assert h["evolution_stage"] == "expert"
    assert h["reinforcement_score"] == 4
    assert h["stability"] == 0.8  # 4/5
    assert 0.0 <= h["freshness"] <= 1.0


def test_dict_round_trip() -> None:
    ev = new_evidence(message="m", confidence=0.7, importance=0.5, reason="x", source_type="semantic")
    restored = Evidence.from_dict(ev).to_dict()
    assert restored == ev

"""Unit tests for the BM25 keyword scorer."""

from __future__ import annotations

from app.application.services.retrieval.bm25 import bm25_scores, tokenize


def test_tokenize_lowercases_and_splits() -> None:
    assert tokenize("Hello, World! 42") == ["hello", "world", "42"]


def test_matching_doc_scores_above_zero() -> None:
    corpus = [tokenize("the capital of france is paris"), tokenize("a goal about reports")]
    scores = bm25_scores(tokenize("paris"), corpus)
    assert scores[0] > 0.0
    assert scores[1] == 0.0


def test_more_relevant_doc_ranks_higher() -> None:
    corpus = [
        tokenize("paris paris paris travel"),
        tokenize("paris once mentioned among many other unrelated words here"),
    ]
    scores = bm25_scores(tokenize("paris"), corpus)
    assert scores[0] > scores[1]


def test_empty_corpus_and_query() -> None:
    assert bm25_scores(tokenize("x"), []) == []
    assert bm25_scores([], [tokenize("a b c")]) == [0.0]

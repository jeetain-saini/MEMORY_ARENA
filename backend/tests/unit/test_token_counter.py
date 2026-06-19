"""Unit tests for the heuristic token counter."""

from __future__ import annotations

from app.application.services.context.tokenization import HeuristicTokenCounter


def test_empty_text_is_zero_tokens() -> None:
    assert HeuristicTokenCounter().count("") == 0
    assert HeuristicTokenCounter().count("   ") == 0


def test_counts_scale_with_length() -> None:
    counter = HeuristicTokenCounter()
    short = counter.count("hi")
    long = counter.count("a much longer piece of text that has many more characters")
    assert short >= 1
    assert long > short


def test_four_chars_per_token_approximation() -> None:
    # "abcdefgh" -> 8 chars / 4 = 2 tokens
    assert HeuristicTokenCounter().count("abcdefgh") == 2

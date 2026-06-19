"""Lexical search via Okapi BM25 (in-memory).

A dependency-free BM25 implementation scored over a fetched candidate corpus.
It is portable and fully testable; at very large scale this can be replaced by
a Postgres full-text index or a dedicated search engine behind the same
KeywordRetriever, with no change to callers.
"""

from __future__ import annotations

import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def bm25_scores(
    query_tokens: list[str],
    corpus_tokens: list[list[str]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Return a BM25 score for each document in ``corpus_tokens``."""
    n_docs = len(corpus_tokens)
    if n_docs == 0 or not query_tokens:
        return [0.0] * n_docs

    doc_lengths = [len(doc) for doc in corpus_tokens]
    avgdl = sum(doc_lengths) / n_docs if n_docs else 0.0

    # Document frequency per unique query term.
    query_terms = set(query_tokens)
    df: dict[str, int] = {}
    for term in query_terms:
        df[term] = sum(1 for doc in corpus_tokens if term in doc)

    idf = {
        term: math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
        for term in query_terms
    }

    scores: list[float] = []
    for doc, dl in zip(corpus_tokens, doc_lengths):
        score = 0.0
        if dl > 0 and avgdl > 0:
            counts: dict[str, int] = {}
            for token in doc:
                if token in query_terms:
                    counts[token] = counts.get(token, 0) + 1
            for term, tf in counts.items():
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * dl / avgdl)
                score += idf[term] * (numerator / denominator)
        scores.append(score)
    return scores

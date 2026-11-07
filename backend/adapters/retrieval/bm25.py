"""In-house Okapi BM25 keyword scorer (spec 007 D5, D6).

No stemming, no stop-word list: IDF down-weights common words, and exact game terms
("hack and slash", "last breath") matter more than recall over inflected forms. Built
in memory from chunk texts; never persisted.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence
from typing import Final

BM25_K1: Final = 1.2
BM25_B: Final = 0.75

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return _TOKEN_RE.findall(normalized)


class BM25Index:
    """Okapi BM25 over a fixed, ordered set of documents."""

    def __init__(self, documents: Sequence[str]) -> None:
        self._doc_count = len(documents)
        self._term_freqs: list[dict[str, int]] = []
        self._doc_lengths: list[int] = []
        doc_freqs: dict[str, int] = {}
        for document in documents:
            tokens = tokenize(document)
            term_freq: dict[str, int] = {}
            for token in tokens:
                term_freq[token] = term_freq.get(token, 0) + 1
            self._term_freqs.append(term_freq)
            self._doc_lengths.append(len(tokens))
            for token in term_freq:
                doc_freqs[token] = doc_freqs.get(token, 0) + 1
        self._doc_freqs = doc_freqs
        self._avg_doc_length = (
            sum(self._doc_lengths) / self._doc_count if self._doc_count else 0.0
        )

    def _idf(self, term: str) -> float:
        df = self._doc_freqs.get(term, 0)
        return math.log(1 + (self._doc_count - df + 0.5) / (df + 0.5))

    def scores(self, query: str) -> list[float]:
        query_terms = set(tokenize(query))
        if not query_terms or self._avg_doc_length == 0:
            return [0.0] * self._doc_count

        idf = {term: self._idf(term) for term in query_terms}
        results: list[float] = []
        for term_freq, doc_length in zip(
            self._term_freqs, self._doc_lengths, strict=True
        ):
            score = 0.0
            for term in query_terms:
                freq = term_freq.get(term, 0)
                if freq == 0:
                    continue
                denom = freq + BM25_K1 * (
                    1 - BM25_B + BM25_B * doc_length / self._avg_doc_length
                )
                score += idf[term] * freq * (BM25_K1 + 1) / denom
            results.append(score)
        return results

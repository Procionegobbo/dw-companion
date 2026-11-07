"""Tests for the in-house BM25 keyword scorer (spec 007 Testing)."""

from __future__ import annotations

from backend.adapters.retrieval.bm25 import BM25Index, tokenize

_HACK_AND_SLASH = (
    "Hack and Slash. When you attack an enemy in melee, roll+STR. Hack and Slash "
    "deals your damage to the enemy."
)
_DEFY_DANGER = (
    "Defy Danger. When you act despite an imminent threat or suffer a calamity, "
    "roll+STAT."
)
_VOLLEY = (
    "Volley. When you take aim and shoot at an enemy at range, roll+DEX and "
    "deal your damage."
)


def test_tokenize() -> None:
    assert tokenize("Hack and Slash\u2019s 10+ (STR)") == [
        "hack",
        "and",
        "slash",
        "s",
        "10",
        "str",
    ]


def test_exact_term_ranks_first() -> None:
    index = BM25Index([_HACK_AND_SLASH, _DEFY_DANGER, _VOLLEY])

    scores = index.scores("hack and slash")

    assert scores[0] > scores[1]
    assert scores[0] > scores[2]
    assert scores[0] == max(scores)


def test_idf_never_negative() -> None:
    index = BM25Index([_HACK_AND_SLASH, _DEFY_DANGER, _VOLLEY])

    # "and" appears in every document; its IDF contribution must stay non-negative.
    scores = index.scores("and")

    assert all(score >= 0 for score in scores)


def test_no_overlap_scores_zero() -> None:
    index = BM25Index([_HACK_AND_SLASH, _DEFY_DANGER, _VOLLEY])

    scores = index.scores("xylophone")

    assert scores == [0.0, 0.0, 0.0]


def test_empty_query_scores_zero() -> None:
    index = BM25Index([_HACK_AND_SLASH, _DEFY_DANGER, _VOLLEY])

    scores = index.scores("")

    assert scores == [0.0, 0.0, 0.0]


def test_length_normalisation() -> None:
    short_doc = "hack hack"
    long_doc = "hack hack filler filler filler filler filler filler"
    index = BM25Index([short_doc, long_doc])

    scores = index.scores("hack")

    assert scores[0] > scores[1]

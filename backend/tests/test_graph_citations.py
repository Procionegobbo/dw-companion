"""Tests for `check_citations` (spec 006 Testing)."""

from __future__ import annotations

from backend.graph.citations import check_citations


def test_all_citations_valid_kept() -> None:
    check = check_citations("A [[x/a]]. B [[x/b]].", {"x/a", "x/b"})

    assert check.text == "A [[x/a]]. B [[x/b]]."
    assert check.valid_ids == ("x/a", "x/b")
    assert check.invalid_ids == ()


def test_invalid_citation_stripped_with_preceding_space() -> None:
    check = check_citations("A [[x/a]]. B [[x/zzz]].", {"x/a"})

    assert check.text == "A [[x/a]]. B."
    assert check.valid_ids == ("x/a",)
    assert check.invalid_ids == ("x/zzz",)


def test_duplicate_citations_deduplicated_in_order() -> None:
    check = check_citations(
        "[[x/b]] first. [[x/a]] second. [[x/b]] third.", {"x/a", "x/b"}
    )

    assert check.valid_ids == ("x/b", "x/a")
    assert check.invalid_ids == ()
    assert check.text.count("[[x/b]]") == 2
    assert check.text.count("[[x/a]]") == 1


def test_no_markers_means_no_valid_ids() -> None:
    check = check_citations("Plain text, no markers.", {"x/a"})

    assert check.valid_ids == ()
    assert check.invalid_ids == ()
    assert check.text == "Plain text, no markers."


def test_all_invalid() -> None:
    check = check_citations("A [[x/a]]. B [[x/b]].", set())

    assert check.valid_ids == ()
    assert check.invalid_ids == ("x/a", "x/b")
    assert "[[x/a]]" not in check.text
    assert "[[x/b]]" not in check.text


def test_non_marker_brackets_untouched() -> None:
    text = "[x/a] and [[ x/a ]]"
    check = check_citations(text, {"x/a"})

    assert check.text == text
    assert check.valid_ids == ()
    assert check.invalid_ids == ()

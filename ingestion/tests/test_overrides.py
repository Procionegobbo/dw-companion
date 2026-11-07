"""Tests for the hand-maintained move overrides (D11)."""

import pytest

from ingestion.overrides import MOVE_OVERRIDES, MoveOverride
from ingestion.pipeline import BuildResult, IngestionError, build

from .conftest import SOURCE_DIR

_DOCUMENTED_OVERRIDE_IDS = {
    "defy-danger",
    "defend",
    "spout-lore",
    "discern-realities",
    "carouse",
    "recruit",
}

_BAND_FIELDS = ("strong_hit", "weak_hit", "miss")


def test_override_set_is_exactly_the_documented_six() -> None:
    assert set(MOVE_OVERRIDES) == _DOCUMENTED_OVERRIDE_IDS
    assert len(MOVE_OVERRIDES) == 6


def test_every_override_targets_an_existing_move(real_build: BuildResult) -> None:
    move_ids = {move.id for move in real_build.moves}
    for move_id in MOVE_OVERRIDES:
        assert move_id in move_ids


def test_override_bands_are_verbatim_substrings_of_move_body(
    real_build: BuildResult,
) -> None:
    moves_by_id = {move.id: move for move in real_build.moves}
    for move_id, override in MOVE_OVERRIDES.items():
        body = moves_by_id[move_id].body_markdown
        for field in _BAND_FIELDS:
            value = getattr(override, field)
            if value is not None:
                assert value in body


def test_every_override_changes_the_automatic_result(real_build: BuildResult) -> None:
    automatic = build(SOURCE_DIR, overrides={})
    automatic_by_id = {move.id: move for move in automatic.moves}
    overridden_by_id = {move.id: move for move in real_build.moves}

    for move_id, override in MOVE_OVERRIDES.items():
        automatic_move = automatic_by_id[move_id]
        overridden_move = overridden_by_id[move_id]
        if override.stat is not None:
            assert overridden_move.stat != automatic_move.stat
        for field in _BAND_FIELDS:
            if getattr(override, field) is not None:
                assert automatic_move.outcomes is not None
                assert overridden_move.outcomes is not None
                assert getattr(overridden_move.outcomes, field) != getattr(
                    automatic_move.outcomes, field
                )


def test_override_with_non_source_text_fails_build() -> None:
    bad_overrides = {
        "hack-and-slash": MoveOverride(
            reason="test", strong_hit="This text does not appear in the source."
        )
    }
    with pytest.raises(IngestionError, match="verbatim substring"):
        build(SOURCE_DIR, overrides=bad_overrides)


def test_override_for_unknown_move_fails_build() -> None:
    bad_overrides = {"not-a-real-move": MoveOverride(reason="test", stat="STR")}
    with pytest.raises(IngestionError, match="unknown move id"):
        build(SOURCE_DIR, overrides=bad_overrides)


def test_override_equal_to_automatic_value_fails_build() -> None:
    bad_overrides = {"hack-and-slash": MoveOverride(reason="test", stat="STR")}
    with pytest.raises(IngestionError, match="equals the automatic value"):
        build(SOURCE_DIR, overrides=bad_overrides)

"""Tests for move extraction (D6-D10)."""

from pathlib import Path
from typing import NamedTuple

import pytest

from ingestion.models import Move, Stat
from ingestion.pipeline import BuildResult, IngestionError, build

from .conftest import make_source

_BASIC_IDS = (
    "hack-and-slash",
    "volley",
    "defy-danger",
    "defend",
    "spout-lore",
    "discern-realities",
    "parley",
    "aid-or-interfere",
)
_SPECIAL_IDS = (
    "last-breath",
    "encumbrance",
    "make-camp",
    "take-watch",
    "undertake-a-perilous-journey",
    "level-up",
    "end-of-session",
    "carouse",
    "supply",
    "recover",
    "recruit",
    "outstanding-warrants",
    "bolster",
)


class _ExpectedMove(NamedTuple):
    category: str
    stat: Stat
    trigger: str
    strong_hit: str
    weak_hit: str
    miss: str | None


_EXPECTED_NAMED_MOVES: dict[str, _ExpectedMove] = {
    "hack-and-slash": _ExpectedMove(
        category="basic",
        stat="STR",
        trigger="When you attack an enemy in melee",
        strong_hit=(
            "On a 10+ you deal your damage to the enemy and avoid their attack. "
            "At your option, you may choose to do +1d6 damage but expose "
            "yourself to the enemy’s attack."
        ),
        weak_hit=(
            "On a 7–9, you deal your damage to the enemy and the enemy makes "
            "an attack against you."
        ),
        miss=None,
    ),
    "defy-danger": _ExpectedMove(
        category="basic",
        stat="VARIES",
        trigger="When you act despite an imminent threat or suffer a calamity",
        strong_hit="On a 10+, you do what you set out to, the threat doesn’t come to bear.",
        weak_hit=(
            "On a 7–9, you stumble, hesitate, or flinch: the GM will offer you "
            "a worse outcome, hard bargain, or ugly choice."
        ),
        miss=None,
    ),
    "volley": _ExpectedMove(
        category="basic",
        stat="DEX",
        trigger="When you take aim and shoot at an enemy at range",
        strong_hit="On a 10+ you have a clear shot—deal your damage.",
        weak_hit=(
            "On a 7–9, choose one (whichever you choose you deal your damage):"
            "\n\n- You have to move to get the shot placing you in danger of "
            "the GM’s choice\n- You have to take what you can get: -1d6 damage"
            "\n- You have to take several shots, reducing your ammo by one."
        ),
        miss=None,
    ),
    "discern-realities": _ExpectedMove(
        category="basic",
        stat="WIS",
        trigger="When you closely study a situation or person",
        strong_hit="On a 10+ ask the GM 3 questions from the list below.",
        weak_hit="On a 7–9 ask 1.",
        miss=None,
    ),
    "last-breath": _ExpectedMove(
        category="special",
        stat="NONE",
        trigger="When you’re dying",
        strong_hit=(
            "On a 10+ you’ve cheated death—you’re in a bad spot but you’re still alive."
        ),
        weak_hit=(
            "On a 7–9 Death will offer you a bargain. Take it and stabilize or "
            "refuse and pass beyond the Black Gates into whatever fate awaits you."
        ),
        miss=(
            "On a miss, your fate is sealed. You’re marked as Death’s own and "
            "you’ll cross the threshold soon. The GM will tell you when."
        ),
    ),
}

_MISS_PRESENT_IDS = {"last-breath", "take-watch", "carouse", "recruit"}
_UNROLLED_IDS = {
    "encumbrance",
    "make-camp",
    "level-up",
    "end-of-session",
    "recover",
    "bolster",
}
_EXPECTED_ROLLED_STATS = {
    "defend": "CON",
    "spout-lore": "INT",
    "parley": "CHA",
    "supply": "CHA",
    "outstanding-warrants": "CHA",
    "aid-or-interfere": "BOND",
    "take-watch": "WIS",
    "undertake-a-perilous-journey": "WIS",
    "carouse": "NONE",
    "recruit": "NONE",
}


def _moves_by_id(real_build: BuildResult) -> dict[str, Move]:
    return {move.id: move for move in real_build.moves}


def test_move_ids_match_source_lists(real_build: BuildResult) -> None:
    assert [m.id for m in real_build.moves if m.category == "basic"] == list(_BASIC_IDS)
    assert [m.id for m in real_build.moves if m.category == "special"] == list(
        _SPECIAL_IDS
    )
    assert len(real_build.moves) == 21


@pytest.mark.parametrize("move_id", list(_EXPECTED_NAMED_MOVES))
def test_named_move_parses_correctly(move_id: str, real_build: BuildResult) -> None:
    move = _moves_by_id(real_build)[move_id]
    expected = _EXPECTED_NAMED_MOVES[move_id]

    assert move.category == expected.category
    assert move.stat == expected.stat
    assert move.trigger == expected.trigger
    assert move.class_ is None
    assert move.section_id == f"moves/{move_id}"
    assert move.outcomes is not None
    assert move.outcomes.strong_hit == expected.strong_hit
    assert move.outcomes.weak_hit == expected.weak_hit
    assert move.outcomes.miss == expected.miss


def test_every_rolled_move_has_trigger_stat_and_hit_bands(
    real_build: BuildResult,
) -> None:
    rolled = [move for move in real_build.moves if move.outcomes is not None]
    assert len(rolled) == 15
    for move in rolled:
        assert move.trigger.strip()
        assert move.stat is not None
        assert move.outcomes is not None
        assert move.outcomes.strong_hit.strip()
        assert move.outcomes.weak_hit.strip()
        assert "miss" in move.outcomes.to_dict()


def test_miss_present_only_where_source_states_it(real_build: BuildResult) -> None:
    ids_with_miss = {
        move.id
        for move in real_build.moves
        if move.outcomes is not None and move.outcomes.miss is not None
    }
    assert ids_with_miss == _MISS_PRESENT_IDS


def test_unrolled_moves_have_no_outcomes_and_no_stat(real_build: BuildResult) -> None:
    by_id = _moves_by_id(real_build)
    for move_id in _UNROLLED_IDS:
        move = by_id[move_id]
        assert move.outcomes is None
        assert move.stat is None
    assert {
        move.id for move in real_build.moves if move.outcomes is None
    } == _UNROLLED_IDS


def test_rolled_move_stats(real_build: BuildResult) -> None:
    by_id = _moves_by_id(real_build)
    for move_id, expected_stat in _EXPECTED_ROLLED_STATS.items():
        assert by_id[move_id].stat == expected_stat


def test_on_a_hit_prefixes_both_hit_bands(real_build: BuildResult) -> None:
    parley = _moves_by_id(real_build)["parley"]
    assert parley.outcomes is not None
    assert parley.outcomes.strong_hit.startswith("On a hit they ask you for something")
    assert parley.outcomes.weak_hit.startswith("On a hit they ask you for something")
    assert parley.outcomes.weak_hit.endswith("right now.")


def test_list_after_band_attaches_to_that_band(real_build: BuildResult) -> None:
    outstanding_warrants = _moves_by_id(real_build)["outstanding-warrants"]
    assert outstanding_warrants.outcomes is not None
    assert outstanding_warrants.outcomes.weak_hit.endswith(
        "- Someone important to you has been put in a bad spot as a result of your actions"
    )


def test_repeated_band_segments_are_joined(real_build: BuildResult) -> None:
    move = _moves_by_id(real_build)["undertake-a-perilous-journey"]
    assert move.outcomes is not None
    assert move.outcomes.strong_hit.count("On a 10+") == 3


def test_move_body_equals_its_section_text(real_build: BuildResult) -> None:
    sections_by_id = {section.id: section for section in real_build.sections}
    for move in real_build.moves:
        assert move.body_markdown == sections_by_id[move.section_id].text_markdown


def test_rolled_move_without_weak_hit_fails_build(tmp_path: Path) -> None:
    source_dir, chapters = make_source(
        tmp_path,
        {
            "moves": (
                "<h1>Basic Moves</h1>"
                '<h2 aid:pstyle="BasicMoveName">Shove</h2>'
                '<p aid:pstyle="NoIndent">When you <strong>shove someone</strong>, '
                "roll+Str. On a 10+ you shove them back.</p>"
            )
        },
    )

    with pytest.raises(IngestionError, match="empty hit band"):
        build(source_dir, chapters=chapters, overrides={})


def test_move_under_unexpected_h1_fails_build(tmp_path: Path) -> None:
    source_dir, chapters = make_source(
        tmp_path,
        {
            "moves": (
                "<h1>Not A Real Category</h1>"
                '<h2 aid:pstyle="BasicMoveName">Shove</h2>'
                '<p aid:pstyle="NoIndent">When you <strong>shove someone</strong>, '
                "roll+Str. On a 10+ you shove them back. On a 7–9 you stumble.</p>"
            )
        },
    )

    with pytest.raises(IngestionError, match="unexpected heading"):
        build(source_dir, chapters=chapters, overrides={})

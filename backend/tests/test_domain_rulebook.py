"""Tests for `backend/domain/rulebook.py`: types, invariants and parsers."""

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from backend.domain.dice import BANDS
from backend.domain.rulebook import (
    ABILITY_STATS,
    STATS,
    Move,
    Outcomes,
    move_from_dict,
    section_from_dict,
)

from .domain_helpers import (
    CHAPTER_SECTION,
    CHILD_SECTION,
    DEFY_DANGER,
    HACK_AND_SLASH,
    LAST_BREATH,
    MAKE_CAMP,
    NAMED_MOVE_FIXTURES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MOVES_JSON = REPO_ROOT / "data" / "normalized" / "moves.json"
SECTIONS_JSON = REPO_ROOT / "data" / "normalized" / "sections.json"


@pytest.mark.parametrize(
    "fixture", NAMED_MOVE_FIXTURES, ids=lambda f: cast(str, f["id"])
)
def test_named_moves_parse(fixture: dict[str, object]) -> None:
    move = move_from_dict(fixture)
    assert move.id == fixture["id"]
    assert move.name == fixture["name"]
    assert move.category == fixture["category"]
    assert move.class_ == fixture["class"]
    assert move.stat == fixture["stat"]
    assert move.trigger == fixture["trigger"]
    assert move.body_markdown == fixture["body_markdown"]
    assert move.section_id == fixture["section_id"]
    assert isinstance(move.outcomes, Outcomes)
    outcomes = cast(dict[str, object], fixture["outcomes"])
    assert move.outcomes.strong_hit == outcomes["strong_hit"]
    assert move.outcomes.weak_hit == outcomes["weak_hit"]
    assert move.outcomes.miss == outcomes["miss"]


def test_last_breath_states_miss() -> None:
    move = move_from_dict(LAST_BREATH)
    assert move.outcomes is not None
    assert move.outcomes.miss is not None


def test_hack_and_slash_miss_is_none() -> None:
    move = move_from_dict(HACK_AND_SLASH)
    assert move.outcomes is not None
    assert move.outcomes.miss is None


def test_extended_stats_parse() -> None:
    varies = move_from_dict(DEFY_DANGER)
    assert varies.stat == "VARIES"

    none_stat = move_from_dict(LAST_BREATH)
    assert none_stat.stat == "NONE"

    bond_fixture = copy.deepcopy(HACK_AND_SLASH)
    bond_fixture["stat"] = "BOND"
    bond = move_from_dict(bond_fixture)
    assert bond.stat == "BOND"


def test_non_rolled_move_parses() -> None:
    move = move_from_dict(MAKE_CAMP)
    assert move.stat is None
    assert move.outcomes is None
    assert move.is_rolled is False


def test_rolled_move_is_rolled() -> None:
    move = move_from_dict(HACK_AND_SLASH)
    assert move.is_rolled is True


def test_outcomes_text_for_each_band() -> None:
    outcomes = Outcomes(strong_hit="strong", weak_hit="weak", miss="miss text")
    assert outcomes.text_for("strong_hit") == "strong"
    assert outcomes.text_for("weak_hit") == "weak"
    assert outcomes.text_for("miss") == "miss text"


_SAMPLE_OUTCOMES = Outcomes(strong_hit="strong", weak_hit="weak", miss=None)


def test_stat_outcomes_consistency_enforced() -> None:
    with pytest.raises(ValueError, match="stat and outcomes must both be set"):
        Move(
            id="hack-and-slash",
            name="Hack and Slash",
            category="basic",
            class_=None,
            stat="STR",
            trigger="When you attack an enemy in melee",
            outcomes=None,
            body_markdown="(body)",
            section_id="moves/hack-and-slash",
        )
    with pytest.raises(ValueError, match="stat and outcomes must both be set"):
        Move(
            id="hack-and-slash",
            name="Hack and Slash",
            category="basic",
            class_=None,
            stat=None,
            trigger="When you attack an enemy in melee",
            outcomes=_SAMPLE_OUTCOMES,
            body_markdown="(body)",
            section_id="moves/hack-and-slash",
        )


def test_class_field_consistency_enforced() -> None:
    with pytest.raises(ValueError, match="class_ must be non-empty"):
        Move(
            id="hack-and-slash",
            name="Hack and Slash",
            category="class",
            class_=None,
            stat="STR",
            trigger="When you attack an enemy in melee",
            outcomes=_SAMPLE_OUTCOMES,
            body_markdown="(body)",
            section_id="moves/hack-and-slash",
        )
    with pytest.raises(ValueError, match="class_ must be null"):
        Move(
            id="hack-and-slash",
            name="Hack and Slash",
            category="basic",
            class_="fighter",
            stat="STR",
            trigger="When you attack an enemy in melee",
            outcomes=_SAMPLE_OUTCOMES,
            body_markdown="(body)",
            section_id="moves/hack-and-slash",
        )
    move = Move(
        id="hack-and-slash",
        name="Hack and Slash",
        category="class",
        class_="fighter",
        stat="STR",
        trigger="When you attack an enemy in melee",
        outcomes=_SAMPLE_OUTCOMES,
        body_markdown="(body)",
        section_id="moves/hack-and-slash",
    )
    assert move.class_ == "fighter"


@pytest.mark.parametrize(
    ("field", "value", "contains"),
    [
        ("id", "Hack and Slash", "id"),
        ("name", "", "name"),
        ("trigger", "   ", "trigger"),
        ("stat", "LUCK", "stat"),
        ("category", "legendary", "category"),
    ],
)
def test_invalid_move_values_rejected(field: str, value: object, contains: str) -> None:
    fixture = copy.deepcopy(HACK_AND_SLASH)
    fixture[field] = value
    with pytest.raises(ValueError, match=contains):
        move_from_dict(fixture)


def test_invalid_move_outcomes_values_rejected() -> None:
    empty_strong = copy.deepcopy(HACK_AND_SLASH)
    cast(dict[str, object], empty_strong["outcomes"])["strong_hit"] = ""
    with pytest.raises(ValueError, match="strong_hit"):
        move_from_dict(empty_strong)

    empty_miss = copy.deepcopy(LAST_BREATH)
    cast(dict[str, object], empty_miss["outcomes"])["miss"] = ""
    with pytest.raises(ValueError, match="miss"):
        move_from_dict(empty_miss)


def test_invalid_move_section_id_rejected() -> None:
    fixture = copy.deepcopy(HACK_AND_SLASH)
    fixture["section_id"] = "moves/"
    with pytest.raises(ValueError, match="section_id"):
        move_from_dict(fixture)


def test_move_from_dict_rejects_non_mapping() -> None:
    with pytest.raises(ValueError, match="mapping"):
        move_from_dict(cast(dict[str, object], ["not", "a", "mapping"]))


def test_move_from_dict_rejects_missing_and_extra_keys() -> None:
    missing = copy.deepcopy(HACK_AND_SLASH)
    del missing["trigger"]
    with pytest.raises(ValueError, match="trigger"):
        move_from_dict(missing)

    extra = copy.deepcopy(HACK_AND_SLASH)
    extra["extra"] = "nope"
    with pytest.raises(ValueError, match="extra"):
        move_from_dict(extra)


def test_move_from_dict_rejects_wrong_types() -> None:
    bad_stat = copy.deepcopy(HACK_AND_SLASH)
    bad_stat["stat"] = 1
    with pytest.raises(ValueError, match="stat must be str or null"):
        move_from_dict(bad_stat)

    bad_outcomes = copy.deepcopy(HACK_AND_SLASH)
    bad_outcomes["outcomes"] = "x"
    with pytest.raises(ValueError, match="outcomes must be a mapping or null"):
        move_from_dict(bad_outcomes)

    missing_miss = copy.deepcopy(HACK_AND_SLASH)
    del cast(dict[str, object], missing_miss["outcomes"])["miss"]
    with pytest.raises(ValueError, match="missing keys"):
        move_from_dict(missing_miss)


def test_sections_parse() -> None:
    chapter = section_from_dict(CHAPTER_SECTION)
    assert chapter.id == CHAPTER_SECTION["id"]
    assert chapter.chapter == CHAPTER_SECTION["chapter"]
    assert chapter.title == CHAPTER_SECTION["title"]
    assert chapter.slug == CHAPTER_SECTION["slug"]
    assert chapter.parent_id == CHAPTER_SECTION["parent_id"]
    assert chapter.order == CHAPTER_SECTION["order"]
    assert chapter.text_markdown == CHAPTER_SECTION["text_markdown"]

    child = section_from_dict(CHILD_SECTION)
    assert child.id == CHILD_SECTION["id"]
    assert child.chapter == CHILD_SECTION["chapter"]
    assert child.title == CHILD_SECTION["title"]
    assert child.slug == CHILD_SECTION["slug"]
    assert child.parent_id == CHILD_SECTION["parent_id"]
    assert child.order == CHILD_SECTION["order"]
    assert child.text_markdown == CHILD_SECTION["text_markdown"]


def test_section_from_dict_rejects_non_mapping() -> None:
    with pytest.raises(ValueError, match="mapping"):
        section_from_dict(cast(dict[str, object], "not-a-mapping"))


def test_section_hierarchy_enforced() -> None:
    chapter_with_parent = copy.deepcopy(CHAPTER_SECTION)
    chapter_with_parent["parent_id"] = "introduction"
    with pytest.raises(ValueError, match="id must equal"):
        section_from_dict(chapter_with_parent)

    child_without_parent = copy.deepcopy(CHILD_SECTION)
    child_without_parent["parent_id"] = None
    with pytest.raises(ValueError, match="id must equal"):
        section_from_dict(child_without_parent)

    child_wrong_id = copy.deepcopy(CHILD_SECTION)
    child_wrong_id["id"] = "moves/wrong-slug"
    with pytest.raises(ValueError, match="id must equal"):
        section_from_dict(child_wrong_id)

    chapter_wrong_slug = copy.deepcopy(CHAPTER_SECTION)
    chapter_wrong_slug["slug"] = "other"
    with pytest.raises(ValueError, match="id must equal"):
        section_from_dict(chapter_wrong_slug)


def test_section_order_rules() -> None:
    negative = copy.deepcopy(CHAPTER_SECTION)
    negative["order"] = -1
    with pytest.raises(ValueError, match="order must be >= 0"):
        section_from_dict(negative)

    boolean = copy.deepcopy(CHAPTER_SECTION)
    boolean["order"] = True
    with pytest.raises(ValueError, match="order must be int, not bool"):
        section_from_dict(boolean)

    empty_text = copy.deepcopy(CHAPTER_SECTION)
    empty_text["text_markdown"] = ""
    section = section_from_dict(empty_text)
    assert section.text_markdown == ""


def test_section_from_dict_rejects_missing_and_extra_keys() -> None:
    missing = copy.deepcopy(CHAPTER_SECTION)
    del missing["order"]
    with pytest.raises(ValueError, match="order"):
        section_from_dict(missing)

    extra = copy.deepcopy(CHAPTER_SECTION)
    extra["extra"] = "nope"
    with pytest.raises(ValueError, match="extra"):
        section_from_dict(extra)


def test_vocabularies() -> None:
    assert STATS == (
        "STR",
        "DEX",
        "CON",
        "INT",
        "WIS",
        "CHA",
        "BOND",
        "VARIES",
        "NONE",
    )
    assert ABILITY_STATS == ("STR", "DEX", "CON", "INT", "WIS", "CHA")
    assert BANDS == ("strong_hit", "weak_hit", "miss")
    assert len(STATS) == 9
    assert len(ABILITY_STATS) == 6
    assert len(BANDS) == 3


def test_committed_moves_json_parses() -> None:
    if not MOVES_JSON.exists():
        pytest.skip("spec 002 output not present")
    raw_moves = json.loads(MOVES_JSON.read_text(encoding="utf-8"))
    moves = [move_from_dict(entry) for entry in raw_moves]
    ids = {move.id for move in moves}
    for expected_id in (
        "hack-and-slash",
        "defy-danger",
        "volley",
        "discern-realities",
        "last-breath",
    ):
        assert expected_id in ids


def test_committed_sections_json_parses() -> None:
    if not SECTIONS_JSON.exists():
        pytest.skip("spec 002 output not present")
    raw_sections = json.loads(SECTIONS_JSON.read_text(encoding="utf-8"))
    sections = [section_from_dict(entry) for entry in raw_sections]
    section_ids = {section.id for section in sections}

    if MOVES_JSON.exists():
        raw_moves = json.loads(MOVES_JSON.read_text(encoding="utf-8"))
        moves = [move_from_dict(entry) for entry in raw_moves]
        for move in moves:
            assert move.section_id in section_ids

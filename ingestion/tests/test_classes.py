"""Tests for class extraction (D15)."""

from pathlib import Path
from typing import NamedTuple

import pytest

from ingestion.models import GameClass
from ingestion.pipeline import BuildResult, IngestionError, build

from .conftest import make_source

_CLASS_IDS_IN_ORDER = (
    "bard",
    "cleric",
    "druid",
    "fighter",
    "paladin",
    "ranger",
    "thief",
    "wizard",
)


class _ExpectedClassStats(NamedTuple):
    max_hp_base: int
    base_damage: str
    load_base: int


_EXPECTED_CLASS_STATS: dict[str, _ExpectedClassStats] = {
    "bard": _ExpectedClassStats(max_hp_base=6, base_damage="d6", load_base=9),
    "cleric": _ExpectedClassStats(max_hp_base=8, base_damage="d6", load_base=10),
    "druid": _ExpectedClassStats(max_hp_base=6, base_damage="d6", load_base=6),
    "fighter": _ExpectedClassStats(max_hp_base=10, base_damage="d10", load_base=12),
    "paladin": _ExpectedClassStats(max_hp_base=10, base_damage="d10", load_base=12),
    "ranger": _ExpectedClassStats(max_hp_base=8, base_damage="d8", load_base=11),
    "thief": _ExpectedClassStats(max_hp_base=6, base_damage="d8", load_base=9),
    "wizard": _ExpectedClassStats(max_hp_base=4, base_damage="d4", load_base=7),
}


def _classes_by_id(real_build: BuildResult) -> dict[str, GameClass]:
    return {game_class.id: game_class for game_class in real_build.classes}


def test_classes_are_the_eight_core_classes_in_order(real_build: BuildResult) -> None:
    assert [game_class.id for game_class in real_build.classes] == list(
        _CLASS_IDS_IN_ORDER
    )
    assert [game_class.order for game_class in real_build.classes] == list(range(8))


@pytest.mark.parametrize("class_id", list(_EXPECTED_CLASS_STATS))
def test_class_stats_match_source(class_id: str, real_build: BuildResult) -> None:
    game_class = _classes_by_id(real_build)[class_id]
    expected = _EXPECTED_CLASS_STATS[class_id]

    assert game_class.max_hp_base == expected.max_hp_base
    assert game_class.base_damage == expected.base_damage
    assert game_class.load_base == expected.load_base
    assert game_class.name == class_id.capitalize()


def test_class_section_ids_resolve(real_build: BuildResult) -> None:
    sections_by_id = {section.id: section for section in real_build.sections}
    for game_class in real_build.classes:
        assert game_class.section_id == game_class.id
        assert game_class.section_id in sections_by_id


def test_missing_class_stat_line_fails_build(tmp_path: Path) -> None:
    source_dir, chapters = make_source(
        tmp_path,
        {
            "fighter": (
                "<h1>The Fighter</h1>"
                '<p aid:pstyle="NoIndent">Your maximum HP is 10+Constitution.</p>'
                '<p aid:pstyle="NoIndent">Your base damage is '
                '<span id="Damage">d10</span>.</p>'
            )
        },
    )

    with pytest.raises(IngestionError, match=r"fighter.*load_base"):
        build(source_dir, chapters=chapters, overrides={})

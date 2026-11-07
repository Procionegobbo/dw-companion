"""Tests for chapter sectioning."""

import re
from pathlib import Path

import pytest

from ingestion.manifest import CHAPTERS, CLASS_CHAPTER_IDS, Chapter
from ingestion.pipeline import BuildResult, IngestionError, build

from .conftest import SOURCE_DIR, make_source

_SECTION_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?$")


def test_manifest_matches_real_source_files() -> None:
    if not SOURCE_DIR.is_dir():
        pytest.fail(
            f"{SOURCE_DIR} is missing - run 'git submodule update --init' "
            "to check out the vendored source."
        )

    manifest_files = {chapter.file for chapter in CHAPTERS}
    real_files = {
        str(path.relative_to(SOURCE_DIR).as_posix())
        for path in SOURCE_DIR.rglob("*.xml")
    }
    assert manifest_files == real_files
    assert len(CHAPTERS) == 37
    assert CLASS_CHAPTER_IDS == (
        "bard",
        "cleric",
        "druid",
        "fighter",
        "paladin",
        "ranger",
        "thief",
        "wizard",
    )


def test_matching_first_h1_is_consumed_as_chapter_heading(tmp_path: Path) -> None:
    source_dir, chapters = make_source(
        tmp_path, {"intro": "<h1>Intro</h1><p>Welcome.</p>"}
    )
    result = build(source_dir, chapters=chapters)

    assert len(result.sections) == 1
    section = result.sections[0]
    assert section.id == "intro"
    assert section.title == "Intro"
    assert section.parent_id is None
    assert section.text_markdown == "Welcome."


def test_non_matching_first_h1_becomes_child_section(tmp_path: Path) -> None:
    # Mirrors Moves.xml: chapter id "moves" -> derived title "Moves", first h1 is
    # "Basic Moves" (different), so it becomes a child section instead of the
    # consumed chapter heading.
    source_dir, chapters = make_source(
        tmp_path, {"moves": "<h1>Basic Moves</h1><p>Hack and Slash text.</p>"}
    )
    # overrides={}: the default MOVE_OVERRIDES target real move ids that don't exist
    # in this synthetic, moveless "moves" chapter.
    result = build(source_dir, chapters=chapters, overrides={})

    assert len(result.sections) == 2
    chapter_section, child_section = result.sections
    assert chapter_section.id == "moves"
    assert chapter_section.title == "Moves"
    assert chapter_section.parent_id is None
    assert child_section.id == "moves/basic-moves"
    assert child_section.title == "Basic Moves"
    assert child_section.parent_id == "moves"


def test_h2_parents_to_latest_h1_else_chapter(tmp_path: Path) -> None:
    body = (
        "<Story><h2>Before Any H1</h2><p>Early.</p></Story>"
        "<Story><h1>First</h1><p>First body.</p>"
        "<h2>Under First</h2><p>Under first body.</p>"
        "<h1>Second</h1><h2>Under Second</h2><p>Under second body.</p></Story>"
    )
    source_dir, chapters = make_source(tmp_path, {"y": body})
    result = build(source_dir, chapters=chapters)

    by_id = {section.id: section for section in result.sections}
    assert by_id["y/before-any-h1"].parent_id == "y"
    assert by_id["y/first"].parent_id == "y"
    assert by_id["y/under-first"].parent_id == "y/first"
    assert by_id["y/second"].parent_id == "y"
    assert by_id["y/under-second"].parent_id == "y/second"


def test_duplicate_heading_in_chapter_gets_numeric_suffix(tmp_path: Path) -> None:
    body = "<h2>Notes</h2><p>First.</p><h2>Notes</h2><p>Second.</p>"
    source_dir, chapters = make_source(tmp_path, {"x": body})
    result = build(source_dir, chapters=chapters)

    ids = [section.id for section in result.sections]
    assert "x/notes" in ids
    assert "x/notes-2" in ids


def test_section_text_excludes_child_sections(tmp_path: Path) -> None:
    body = "<h1>Parent</h1><p>Parent body.</p><h2>Child</h2><p>Child body.</p>"
    source_dir, chapters = make_source(tmp_path, {"z": body})
    result = build(source_dir, chapters=chapters)

    by_id = {section.id: section for section in result.sections}
    assert by_id["z/parent"].text_markdown == "Parent body."
    assert by_id["z/child"].text_markdown == "Child body."


def test_build_fails_when_source_has_unlisted_file(tmp_path: Path) -> None:
    source_dir, chapters = make_source(tmp_path, {"a": "<h1>A</h1>"})
    (source_dir / "extra.xml").write_text(
        '<Root xmlns:aid="http://ns.adobe.com/AdobeInDesign/4.0/"/>', encoding="utf-8"
    )

    with pytest.raises(IngestionError, match=re.escape("extra.xml")):
        build(source_dir, chapters=chapters)


def test_build_fails_when_manifest_file_is_missing(tmp_path: Path) -> None:
    source_dir, chapters = make_source(tmp_path, {"a": "<h1>A</h1>"})
    missing_chapter = Chapter("missing.xml", "missing", "Missing")

    with pytest.raises(IngestionError, match=re.escape("missing.xml")):
        build(source_dir, chapters=(*chapters, missing_chapter))


def test_build_fails_on_malformed_xml(tmp_path: Path) -> None:
    source_dir, chapters = make_source(tmp_path, {"broken": "<h1>Broken</h1>"})
    (source_dir / "broken.xml").write_text("<Root><unclosed></Root>", encoding="utf-8")

    with pytest.raises(IngestionError, match=re.escape("broken.xml")):
        build(source_dir, chapters=chapters)


def test_every_chapter_has_a_root_section_in_manifest_order(
    real_build: BuildResult,
) -> None:
    chapter_sections = [s for s in real_build.sections if s.parent_id is None]
    assert [s.id for s in chapter_sections] == [c.id for c in CHAPTERS]


def test_section_ids_unique_and_well_formed(real_build: BuildResult) -> None:
    ids = [section.id for section in real_build.sections]
    assert len(ids) == len(set(ids))
    for section_id in ids:
        assert _SECTION_ID_RE.match(section_id), section_id


def test_parent_ids_resolve_to_earlier_sections(real_build: BuildResult) -> None:
    seen: set[str] = set()
    for section in real_build.sections:
        if section.parent_id is not None:
            assert section.parent_id in seen
        seen.add(section.id)


def test_order_is_contiguous_from_zero(real_build: BuildResult) -> None:
    orders = [section.order for section in real_build.sections]
    assert orders == list(range(len(orders)))


def test_moves_chapter_hierarchy(real_build: BuildResult) -> None:
    by_id = {section.id: section for section in real_build.sections}
    assert by_id["moves/basic-moves"].parent_id == "moves"
    assert by_id["moves/hack-and-slash"].parent_id == "moves/basic-moves"
    assert by_id["moves/bolster"].parent_id == "moves/special-moves"

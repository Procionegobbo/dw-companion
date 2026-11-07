"""Build, serialize and write the three normalized JSON files from the source XML.

Everything is built in memory; `write()` is the only function that touches the
filesystem, and only under `--out`, and only once the caller (`ingestion/cli.py`) has
confirmed the unknown-markup gate passes - see the spec's Architecture / Design
Overview ("build in memory, write only after all gates pass").
"""

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ingestion.classes import extract_classes
from ingestion.manifest import CHAPTERS, CLASS_CHAPTER_IDS, Chapter
from ingestion.markdown import UnknownMarkup
from ingestion.models import GameClass, Move, Section
from ingestion.moves import apply_overrides, extract_moves, validate_moves
from ingestion.overrides import MOVE_OVERRIDES, MoveOverride
from ingestion.sections import build_chapter_sections

DEFAULT_MAX_UNKNOWN = 0

_SECTION_ID_RE: re.Pattern[str] = re.compile(
    r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?$"
)


class IngestionError(Exception):
    """Raised for any build-time failure - see the spec's Validation Rules."""


@dataclass(frozen=True, slots=True)
class BuildResult:
    sections: tuple[Section, ...]
    moves: tuple[Move, ...]
    classes: tuple[GameClass, ...]
    unknown: Mapping[str, int]
    overrides_applied: int

    @property
    def unknown_total(self) -> int:
        return sum(self.unknown.values())


def _check_chapter_ids_unique(chapters: Sequence[Chapter]) -> None:
    seen: set[str] = set()
    for chapter in chapters:
        if chapter.id in seen:
            raise IngestionError(f"duplicate chapter id: {chapter.id}")
        seen.add(chapter.id)


def _check_manifest_matches_source(
    source_dir: Path, chapters: Sequence[Chapter]
) -> None:
    manifest_files = {chapter.file for chapter in chapters}
    real_files = {
        path.relative_to(source_dir).as_posix() for path in source_dir.rglob("*.xml")
    }
    missing = sorted(manifest_files - real_files)
    unlisted = sorted(real_files - manifest_files)
    if not missing and not unlisted:
        return
    parts: list[str] = []
    if missing:
        parts.append(f"missing from source: {', '.join(missing)}")
    if unlisted:
        parts.append(f"not in manifest: {', '.join(unlisted)}")
    raise IngestionError("manifest/source mismatch - " + "; ".join(parts))


def _parse_chapter(source_dir: Path, chapter: Chapter) -> ET.Element:
    path = source_dir / chapter.file
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as error:
        raise IngestionError(f"malformed XML in {chapter.file}: {error}") from error


def _validate_sections(sections: Sequence[Section]) -> None:
    seen_ids: set[str] = set()
    for section in sections:
        if not section.title.strip():
            raise IngestionError(f"section {section.id} has an empty title")
        if section.id in seen_ids:
            raise IngestionError(f"duplicate section id: {section.id}")
        if not _SECTION_ID_RE.match(section.id):
            raise IngestionError(f"malformed section id: {section.id}")
        if section.parent_id is not None and section.parent_id not in seen_ids:
            raise IngestionError(
                f"section {section.id} has parent_id {section.parent_id!r} that "
                "does not refer to an earlier section"
            )
        seen_ids.add(section.id)


def build(
    source_dir: Path,
    chapters: Sequence[Chapter] = CHAPTERS,
    overrides: Mapping[str, MoveOverride] = MOVE_OVERRIDES,
) -> BuildResult:
    """Build every section (and, if present, the `moves` chapter's moves) from
    `chapters`' XML files under `source_dir`.

    Raises `IngestionError` if `source_dir` is not a directory, if `chapters` disagrees
    with the `.xml` files actually present under it, if two chapters share an id, if a
    file fails to parse, or if a built section, move or override fails validation.
    """
    if not source_dir.is_dir():
        raise IngestionError(f"source directory does not exist: {source_dir}")

    _check_chapter_ids_unique(chapters)
    _check_manifest_matches_source(source_dir, chapters)

    unknown = UnknownMarkup()
    sections: list[Section] = []
    moves_chapter: Chapter | None = None
    moves_root: ET.Element | None = None
    class_roots: dict[str, ET.Element] = {}
    order = 0
    for chapter in chapters:
        root = _parse_chapter(source_dir, chapter)
        if chapter.id == "moves":
            moves_chapter, moves_root = chapter, root
        if chapter.id in CLASS_CHAPTER_IDS:
            class_roots[chapter.id] = root
        chapter_sections, order = build_chapter_sections(
            chapter, root, unknown, chapter.file, order
        )
        sections.extend(chapter_sections)

    _validate_sections(sections)

    moves: tuple[Move, ...] = ()
    overrides_applied = 0
    if moves_chapter is not None and moves_root is not None:
        sections_by_id = {section.id: section for section in sections}
        raw_moves = extract_moves(moves_chapter, moves_root, sections_by_id)
        validate_moves(raw_moves)
        moves = apply_overrides(raw_moves, overrides)
        overrides_applied = len(overrides)

    classes: tuple[GameClass, ...] = ()
    if class_roots:
        classes = extract_classes(chapters, class_roots)

    return BuildResult(
        sections=tuple(sections),
        moves=moves,
        classes=classes,
        unknown=dict(unknown.counts),
        overrides_applied=overrides_applied,
    )


def _dump(rows: list[dict[str, object]]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"


def serialize(result: BuildResult) -> dict[str, str]:
    """Return `{"sections.json": text, "moves.json": text, "classes.json": text}`."""
    return {
        "sections.json": _dump([section.to_dict() for section in result.sections]),
        "moves.json": _dump([move.to_dict() for move in result.moves]),
        "classes.json": _dump([game_class.to_dict() for game_class in result.classes]),
    }


def write(result: BuildResult, out_dir: Path) -> None:
    """Write the three serialized files to `out_dir`, creating it if needed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, text in serialize(result).items():
        (out_dir / filename).write_text(text, encoding="utf-8", newline="\n")

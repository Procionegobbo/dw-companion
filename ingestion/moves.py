"""Extracts the 21 basic and special moves from the `moves` chapter (D6-D10).

Walks the same flattened item sequence `ingestion/sections.py` builds sections from,
tracking the most recently seen `h1` text to resolve each move's `category`, and
deriving `trigger`, `stat` and `outcomes` from the raw XML elements between one move
heading and the next. `body_markdown` is simply the already-built section's own
`text_markdown` (D4: the same text, rendered once) - the shared Markdown renderer is
used here only to get normalised, escaped text for outcome-band segmentation, through
a throwaway `UnknownMarkup` so sectioning remains the only place unknowns are counted.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import replace

from ingestion.manifest import Chapter
from ingestion.markdown import (
    AID,
    UnknownMarkup,
    normalize_text,
    plain_text,
    render_block,
    render_inline,
    slugify,
)
from ingestion.models import Category, Move, Outcomes, Section, Stat
from ingestion.overrides import MoveOverride
from ingestion.sections import flatten_items

_MOVE_HEADING_PSTYLE = "BasicMoveName"
_STRONG_TAGS = ("strong", "Strong")

_CATEGORY_BY_H1: dict[str, Category] = {
    "Basic Moves": "basic",
    "Special Moves": "special",
}
_STAT_BY_WORD: dict[str, Stat] = {
    "str": "STR",
    "dex": "DEX",
    "con": "CON",
    "int": "INT",
    "wis": "WIS",
    "cha": "CHA",
    "bond": "BOND",
}
_BAND_BY_MARKER: dict[str, str] = {
    "10+": "strong",
    "7–9": "weak",
    "7-9": "weak",
    "hit": "hit",
    "miss": "miss",
    "6-": "miss",
}

_TRAILING_PUNCT_RE = re.compile(r"[\s,.;:]+$")
_STAT_RE = re.compile(
    r"\brolls?\s*\+\s*(Str|Dex|Con|Int|Wis|Cha|Bond)\b", re.IGNORECASE
)
_MARKER_RE = re.compile(r"On a (10\+|7[–-]9|hit|miss|6-)")


def _ingestion_error(message: str) -> Exception:
    """Build an `IngestionError`.

    Imported lazily (inside this function, not at module scope) because
    `ingestion.pipeline` imports this module to call `extract_moves`/`apply_overrides`;
    a module-level import back here would be circular.
    """
    from ingestion.pipeline import IngestionError

    return IngestionError(message)


def extract_moves(
    chapter: Chapter,
    root: ET.Element,
    sections_by_id: Mapping[str, Section],
) -> tuple[Move, ...]:
    """Build every move from the `moves` chapter's XML, in document order."""
    moves: list[Move] = []
    latest_h1_text: str | None = None
    current_heading: ET.Element | None = None
    current_block: list[ET.Element] = []

    def finalize() -> None:
        if current_heading is not None:
            moves.append(
                _build_move(
                    chapter,
                    current_heading,
                    current_block,
                    latest_h1_text,
                    sections_by_id,
                )
            )

    for item in flatten_items(root):
        if isinstance(item, str):
            continue
        if item.tag == "h1":
            finalize()
            current_heading, current_block = None, []
            latest_h1_text = plain_text(item)
            continue
        if item.tag == "h2":
            finalize()
            current_block = []
            current_heading = (
                item
                if item.attrib.get(AID + "pstyle") == _MOVE_HEADING_PSTYLE
                else None
            )
            continue
        if current_heading is not None:
            current_block.append(item)

    finalize()
    return tuple(moves)


def _build_move(
    chapter: Chapter,
    heading: ET.Element,
    block: Sequence[ET.Element],
    enclosing_h1: str | None,
    sections_by_id: Mapping[str, Section],
) -> Move:
    name = plain_text(heading)
    move_id = slugify(name)
    category = _resolve_category(enclosing_h1, move_id)

    section_id = f"{chapter.id}/{move_id}"
    section = sections_by_id.get(section_id)
    if section is None:
        raise _ingestion_error(
            f"move {move_id!r} has no matching section {section_id!r}"
        )

    first_paragraph = next((el for el in block if el.tag == "p"), None)
    if first_paragraph is None:
        raise _ingestion_error(
            f"move {move_id!r} has no paragraph to take a trigger from"
        )
    trigger = _extract_trigger(first_paragraph, move_id)

    outcomes = _extract_outcomes(block)
    stat: Stat | None = _extract_stat(block) if outcomes is not None else None

    return Move(
        id=move_id,
        name=name,
        category=category,
        class_=None,
        stat=stat,
        trigger=trigger,
        outcomes=outcomes,
        body_markdown=section.text_markdown,
        section_id=section_id,
    )


def _resolve_category(enclosing_h1: str | None, move_id: str) -> Category:
    if enclosing_h1 not in _CATEGORY_BY_H1:
        raise _ingestion_error(
            f"move {move_id!r} is under unexpected heading {enclosing_h1!r}; expected "
            '"Basic Moves" or "Special Moves"'
        )
    return _CATEGORY_BY_H1[enclosing_h1]


def _extract_trigger(first_paragraph: ET.Element, move_id: str) -> str:
    """The plain text from paragraph start through the end of its last strong/Strong."""
    strongs = [child for child in first_paragraph if child.tag in _STRONG_TAGS]
    if not strongs:
        raise _ingestion_error(
            f"move {move_id!r} has no strong text in its first paragraph"
        )
    last_strong = strongs[-1]

    parts: list[str] = [first_paragraph.text or ""]
    for child in first_paragraph:
        parts.append("".join(child.itertext()))
        if child is last_strong:
            break
        parts.append(child.tail or "")

    text = normalize_text("".join(parts)).strip()
    return _TRAILING_PUNCT_RE.sub("", text)


def _extract_stat(block: Sequence[ET.Element]) -> Stat:
    """First `roll+STAT` match across the block's `p` elements, else `"NONE"`."""
    for element in block:
        if element.tag != "p":
            continue
        match = _STAT_RE.search(plain_text(element))
        if match:
            return _STAT_BY_WORD[match.group(1).lower()]
    return "NONE"


def _extract_outcomes(block: Sequence[ET.Element]) -> Outcomes | None:
    bands = {"strong": "", "weak": "", "miss": ""}
    last_band: str | None = None
    found_marker = False

    def add(band: str, text: str, separator: str = " ") -> None:
        current = bands[band]
        bands[band] = text if not current else f"{current}{separator}{text}"

    for element in block:
        if element.tag == "p":
            text = render_inline(element, UnknownMarkup(), "")
            matches = list(_MARKER_RE.finditer(text))
            if not matches:
                last_band = None
                continue
            found_marker = True
            for index, match in enumerate(matches):
                end = (
                    matches[index + 1].start()
                    if index + 1 < len(matches)
                    else len(text)
                )
                segment = text[match.start() : end].strip()
                marker_band = _BAND_BY_MARKER[match.group(1)]
                if marker_band == "hit":
                    add("strong", segment)
                    add("weak", segment)
                else:
                    add(marker_band, segment)
            last_band = _BAND_BY_MARKER[matches[-1].group(1)]
        elif element.tag in ("ul", "ol"):
            if last_band is not None:
                list_text = render_block(element, UnknownMarkup(), "")
                if list_text:
                    if last_band == "hit":
                        add("strong", list_text, separator="\n\n")
                        add("weak", list_text, separator="\n\n")
                    else:
                        add(last_band, list_text, separator="\n\n")
            last_band = None
        else:
            last_band = None

    if not found_marker:
        return None
    return Outcomes(
        strong_hit=bands["strong"],
        weak_hit=bands["weak"],
        miss=bands["miss"] or None,
    )


def validate_moves(moves: Sequence[Move]) -> None:
    """Move validation rule: resolvable category (checked in `_resolve_category`),
    unique id, non-empty trigger, and outcomes/stat agreement."""
    seen_ids: set[str] = set()
    for move in moves:
        if move.id in seen_ids:
            raise _ingestion_error(f"duplicate move id: {move.id}")
        seen_ids.add(move.id)
        if not move.trigger.strip():
            raise _ingestion_error(f"move {move.id!r} has an empty trigger")
        if move.outcomes is not None:
            if (
                not move.outcomes.strong_hit.strip()
                or not move.outcomes.weak_hit.strip()
            ):
                raise _ingestion_error(f"move {move.id!r} has an empty hit band")
            if move.stat is None:
                raise _ingestion_error(f"move {move.id!r} has outcomes but no stat")
        elif move.stat is not None:
            raise _ingestion_error(
                f"move {move.id!r} has no outcomes but a non-null stat"
            )


def apply_overrides(
    moves: Sequence[Move], overrides: Mapping[str, MoveOverride]
) -> tuple[Move, ...]:
    moves_by_id = {move.id: move for move in moves}
    for move_id in overrides:
        if move_id not in moves_by_id:
            raise _ingestion_error(f"override for unknown move id: {move_id!r}")

    return tuple(
        _apply_override(move, overrides[move.id]) if move.id in overrides else move
        for move in moves
    )


def _apply_override(move: Move, override: MoveOverride) -> Move:
    stat = move.stat
    if override.stat is not None:
        if override.stat == move.stat:
            raise _ingestion_error(
                f"override for {move.id!r} field 'stat' equals the automatic value"
            )
        stat = override.stat

    outcomes = move.outcomes
    if (
        override.strong_hit is not None
        or override.weak_hit is not None
        or override.miss is not None
    ):
        if outcomes is None:
            raise _ingestion_error(
                f"override for {move.id!r} sets a band but the move has outcomes: null"
            )
        strong_hit = outcomes.strong_hit
        if override.strong_hit is not None:
            _check_band_override(
                move, "strong_hit", outcomes.strong_hit, override.strong_hit
            )
            strong_hit = override.strong_hit
        weak_hit = outcomes.weak_hit
        if override.weak_hit is not None:
            _check_band_override(move, "weak_hit", outcomes.weak_hit, override.weak_hit)
            weak_hit = override.weak_hit
        miss = outcomes.miss
        if override.miss is not None:
            _check_band_override(move, "miss", outcomes.miss, override.miss)
            miss = override.miss
        outcomes = Outcomes(strong_hit=strong_hit, weak_hit=weak_hit, miss=miss)

    return replace(move, stat=stat, outcomes=outcomes)


def _check_band_override(
    move: Move, field_name: str, current: str | None, value: str
) -> None:
    if value not in move.body_markdown:
        raise _ingestion_error(
            f"override for {move.id!r} field {field_name!r} is not a verbatim "
            "substring of the move's body_markdown"
        )
    if value == current:
        raise _ingestion_error(
            f"override for {move.id!r} field {field_name!r} equals the automatic value"
        )

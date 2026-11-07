"""Tolerant, loud Markdown renderer for the source's InDesign-flavoured XML.

Renders a single element's inline contents (`render_inline`) or a single block-level
element or loose text node (`render_block`) to GitHub-flavoured Markdown, following
exactly the tag, attribute, paragraph-style and character-style inventory verified
against the pinned source and recorded in `docs/source-notes.md`. Anything outside that
inventory is still rendered (its text is never lost) but is counted by `UnknownMarkup`
and logged at `WARNING`, so an upstream change shows up as a build failure rather than
silently-dropped text.
"""

import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from typing import Final

logger = logging.getLogger("ingestion")

AID: Final[str] = "{http://ns.adobe.com/AdobeInDesign/4.0/}"

KNOWN_TAGS: Final[frozenset[str]] = frozenset(
    {
        "p",
        "li",
        "span",
        "em",
        "h3",
        "ul",
        "strong",
        "h2",
        "div",
        "h4",
        "h1",
        "Root",
        "Body",
        "TableBody",
        "Cell",
        "Story",
        "Strong",
        "TableHeader",
        "ol",
        "Center",
        "StatTable",
    }
)

KNOWN_ATTRS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "aid:pstyle",
        "aid:cstyle",
        "aid:table",
        "aid:crows",
        "aid:ccols",
        "aid:ccolwidth",
        "aid:theader",
        "aid:trows",
        "aid:tcols",
    }
)

KNOWN_PSTYLES: Final[frozenset[str]] = frozenset(
    {
        "BackerList",
        "BackerListNoIndent",
        "BasicMoveName",
        "Example",
        "ExampleDialogue",
        "ExampleDialogueFirstLine",
        "ExampleDialogueLastLine",
        "Exampleli",
        "Instructions",
        "InstructionsAfterHeader",
        "Item",
        "ItemDescription",
        "Lastli",
        "MagicItem",
        "MonsterDescription",
        "MonsterName",
        "MonsterQualities",
        "MonsterStats",
        "MoveFirstLine",
        "MoveLastLine",
        "MoveName",
        "MoveOneLine",
        "NoIndent",
        "NumberedList",
        "Option",
        "ReNumberedList",
        "Requirement",
        "SpellName",
        "li",
    }
)

KNOWN_CSTYLES: Final[frozenset[str]] = frozenset({"Tags", "SpellName"})

_HEADING_PSTYLES: Final[frozenset[str]] = frozenset(
    {"MonsterName", "SpellName", "MagicItem"}
)
_BLOCKQUOTE_PSTYLES: Final[frozenset[str]] = frozenset(
    {
        "Example",
        "ExampleDialogue",
        "ExampleDialogueFirstLine",
        "ExampleDialogueLastLine",
    }
)

_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_MARKDOWN_CHARS_RE: Final[re.Pattern[str]] = re.compile(r"([\\*_`\[\]])")
_BULLET_MARKER_RE: Final[re.Pattern[str]] = re.compile(r"[-+*] ")
_NUMBERED_MARKER_RE: Final[re.Pattern[str]] = re.compile(r"\d+[.)] ")
_SLUG_RUN_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")

_ZERO_WIDTH_SPACE: Final[str] = "​"
_OUTCOME_MARKER: Final[str] = "✴"


@dataclass(slots=True)
class UnknownMarkup:
    """Counts occurrences of markup outside the known inventory and logs each one."""

    counts: Counter[str] = field(default_factory=Counter[str])

    def record(self, key: str, file: str) -> None:
        self.counts[key] += 1
        logger.warning("unknown %s in %s", key, file)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _attr_short_name(raw_key: str) -> str:
    if raw_key.startswith(AID):
        return "aid:" + raw_key[len(AID) :]
    return raw_key


def _check_element(el: ET.Element, unknown: UnknownMarkup, file: str) -> None:
    """Record any tag, attribute, pstyle or cstyle value outside the known inventory."""
    if el.tag not in KNOWN_TAGS:
        unknown.record(f"tag:{el.tag}", file)
    for raw_key in el.attrib:
        short = _attr_short_name(raw_key)
        if short not in KNOWN_ATTRS:
            unknown.record(f"attr:{short}", file)
    pstyle = el.attrib.get(AID + "pstyle")
    if pstyle is not None and pstyle not in KNOWN_PSTYLES:
        unknown.record(f"pstyle:{pstyle}", file)
    cstyle = el.attrib.get(AID + "cstyle")
    if cstyle is not None and cstyle not in KNOWN_CSTYLES:
        unknown.record(f"cstyle:{cstyle}", file)


def _collapse_and_strip_markers(text: str) -> str:
    text = text.replace(_OUTCOME_MARKER, "").replace(_ZERO_WIDTH_SPACE, "")
    return _WHITESPACE_RE.sub(" ", text)


def _escape_markdown_chars(text: str) -> str:
    return _MARKDOWN_CHARS_RE.sub(r"\\\1", text)


def _normalize_inline_text(text: str) -> str:
    return _escape_markdown_chars(_collapse_and_strip_markers(text))


def plain_text(el: ET.Element) -> str:
    """Concatenated text of the element and descendants: normalised, no Markdown."""
    return _collapse_and_strip_markers("".join(el.itertext())).strip()


def normalize_text(text: str) -> str:
    """Collapse whitespace runs to one space and strip `✴`/zero-width-space markers.

    Used where a caller needs plain-text normalisation of a hand-assembled fragment
    (not a whole element) - e.g. move trigger extraction in `ingestion/moves.py`.
    """
    return _collapse_and_strip_markers(text)


def _wrap_emphasis(inner: str, marker: str) -> str:
    stripped = inner.strip()
    if not stripped:
        return ""
    leading = inner[: len(inner) - len(inner.lstrip())]
    trailing = inner[len(inner.rstrip()) :]
    return f"{leading}{marker}{stripped}{marker}{trailing}"


def render_inline(el: ET.Element, unknown: UnknownMarkup, file: str) -> str:
    """Render the inline contents (text and children) of `el` as Markdown."""
    parts: list[str] = []
    if el.text:
        parts.append(_normalize_inline_text(el.text))
    for child in el:
        _check_element(child, unknown, file)
        parts.append(_render_inline_child(child, unknown, file))
        if child.tail:
            parts.append(_normalize_inline_text(child.tail))
    return "".join(parts).strip()


def _render_inline_child(el: ET.Element, unknown: UnknownMarkup, file: str) -> str:
    if el.tag == "em":
        return _wrap_emphasis(render_inline(el, unknown, file), "*")
    if el.tag in ("strong", "Strong"):
        return _wrap_emphasis(render_inline(el, unknown, file), "**")
    if el.tag == "span":
        inner = render_inline(el, unknown, file)
        if el.attrib.get(AID + "cstyle") == "Tags":
            return _wrap_emphasis(inner, "*")
        return inner
    # Unknown (or otherwise unhandled) inline tag: keep the text, already counted above.
    return render_inline(el, unknown, file)


def _escape_block_marker(text: str) -> str:
    if not text:
        return text
    if text[0] in "#>":
        return "\\" + text
    if _BULLET_MARKER_RE.match(text) or _NUMBERED_MARKER_RE.match(text):
        return "\\" + text
    return text


def _render_paragraph(el: ET.Element, unknown: UnknownMarkup, file: str) -> str:
    inline = render_inline(el, unknown, file)
    if not inline:
        return ""
    text = _escape_block_marker(inline)
    pstyle = el.attrib.get(AID + "pstyle")
    if pstyle in _HEADING_PSTYLES:
        return f"#### {text}"
    if pstyle in _BLOCKQUOTE_PSTYLES:
        return f"> {text}"
    if pstyle == "Requirement":
        return f"*{text}*"
    return text


def _render_list(
    el: ET.Element, unknown: UnknownMarkup, file: str, *, ordered: bool
) -> str:
    lines: list[str] = []
    number = 0
    for li in el.findall("li"):
        _check_element(li, unknown, file)
        inline = render_inline(li, unknown, file)
        if not inline:
            continue
        text = _escape_block_marker(inline)
        if ordered:
            number += 1
            lines.append(f"{number}. {text}")
        else:
            lines.append(f"- {text}")
    return "\n".join(lines)


def _render_stat_table(
    stat_table: ET.Element, unknown: UnknownMarkup, file: str
) -> str:
    _check_element(stat_table, unknown, file)
    tcols_raw = stat_table.attrib.get(AID + "tcols")
    tcols = int(tcols_raw) if tcols_raw else 1
    header_cells: list[str] = []
    body_cells: list[str] = []
    for cell in stat_table:
        _check_element(cell, unknown, file)
        for descendant in cell:
            _check_element(descendant, unknown, file)
        text = plain_text(cell)
        if AID + "theader" in cell.attrib:
            header_cells.append(text)
        else:
            body_cells.append(text)
    lines = [
        "| " + " | ".join(header_cells) + " |",
        "| " + " | ".join(["---"] * len(header_cells)) + " |",
    ]
    for start in range(0, len(body_cells), tcols):
        row = body_cells[start : start + tcols]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_block(block: ET.Element | str, unknown: UnknownMarkup, file: str) -> str:
    """Render one block: an element, or loose text from inside a container."""
    if isinstance(block, str):
        text = _collapse_and_strip_markers(block).strip()
        if not text:
            return ""
        return _escape_block_marker(_escape_markdown_chars(text))

    el = block
    _check_element(el, unknown, file)

    if el.tag == "p":
        return _render_paragraph(el, unknown, file)
    if el.tag in ("h3", "h4"):
        inline = render_inline(el, unknown, file)
        if not inline:
            return ""
        marker = "### " if el.tag == "h3" else "#### "
        return f"{marker}{inline}"
    if el.tag == "ul":
        return _render_list(el, unknown, file, ordered=False)
    if el.tag == "ol":
        return _render_list(el, unknown, file, ordered=True)
    if el.tag == "Center":
        stat_table = el.find("StatTable")
        if stat_table is not None:
            return _render_stat_table(stat_table, unknown, file)
        return ""

    # Unknown (or otherwise unhandled) block tag: render its contents as a paragraph.
    inline = render_inline(el, unknown, file)
    if not inline:
        return ""
    return _escape_block_marker(inline)


def slugify(text: str) -> str:
    """NFKD-normalise, drop accents, lowercase, replace non-alphanumerics with `-`."""
    normalized = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    lowered = without_marks.lower().replace("’", "").replace("'", "")
    lowered = lowered.replace("&", " and ")
    return _SLUG_RUN_RE.sub("-", lowered).strip("-")

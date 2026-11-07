"""Extracts the minimal class stat block for each `CLASS_CHAPTER_IDS` chapter (D15).

Reads each class chapter's own parsed XML directly - the three stat lines are a
handful of plain paragraphs and one tagged `span`, so there is no need to go through
section building or the shared Markdown renderer. Regexes run over the chapter's
plain paragraph text (`docs/source-notes.md` section 6 covers the source convention);
a missing stat line raises `IngestionError` naming the class and the field.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence

from ingestion.manifest import CLASS_CHAPTER_IDS, Chapter
from ingestion.markdown import plain_text
from ingestion.models import GameClass

_HP_RE = re.compile(r"Your maximum HP is (\d+)\+Constitution")
_LOAD_RE = re.compile(r"Your load is (\d+)\+Str")
_DAMAGE_RE = re.compile(r"^d\d+$")
_LEADING_THE_RE = re.compile(r"^The\s+", re.IGNORECASE)


def _ingestion_error(message: str) -> Exception:
    """Build an `IngestionError`.

    Imported lazily (inside this function, not at module scope) because
    `ingestion.pipeline` imports this module to call `extract_classes`; a module-level
    import back here would be circular.
    """
    from ingestion.pipeline import IngestionError

    return IngestionError(message)


def _class_name(chapter: Chapter, root: ET.Element) -> str:
    for element in root.iter("h1"):
        return _LEADING_THE_RE.sub("", plain_text(element))
    raise _ingestion_error(f"class {chapter.id!r} has no h1 to take a name from")


def _paragraphs_text(root: ET.Element) -> str:
    return "\n".join(plain_text(p) for p in root.iter("p"))


def _damage_text(root: ET.Element) -> str | None:
    for span in root.iter("span"):
        if span.attrib.get("id") == "Damage":
            return plain_text(span)
    return None


def _extract_positive_int(
    chapter: Chapter, paragraphs: str, pattern: re.Pattern[str], field: str
) -> int:
    match = pattern.search(paragraphs)
    if match is None:
        raise _ingestion_error(f"class {chapter.id!r} is missing its {field} stat line")
    value = int(match.group(1))
    if value <= 0:
        raise _ingestion_error(
            f"class {chapter.id!r} has a non-positive {field}: {value}"
        )
    return value


def _extract_base_damage(chapter: Chapter, root: ET.Element) -> str:
    damage = _damage_text(root)
    if damage is None:
        raise _ingestion_error(
            f"class {chapter.id!r} is missing its base_damage stat line"
        )
    if not _DAMAGE_RE.match(damage):
        raise _ingestion_error(
            f"class {chapter.id!r} has a malformed base_damage: {damage!r}"
        )
    return damage


def extract_class(chapter: Chapter, root: ET.Element, order: int) -> GameClass:
    """Build one class's stat block from its chapter's parsed XML."""
    name = _class_name(chapter, root)
    paragraphs = _paragraphs_text(root)

    max_hp_base = _extract_positive_int(chapter, paragraphs, _HP_RE, "max_hp_base")
    load_base = _extract_positive_int(chapter, paragraphs, _LOAD_RE, "load_base")
    base_damage = _extract_base_damage(chapter, root)

    return GameClass(
        id=chapter.id,
        name=name,
        section_id=chapter.id,
        order=order,
        max_hp_base=max_hp_base,
        base_damage=base_damage,
        load_base=load_base,
    )


def extract_classes(
    chapters: Sequence[Chapter], roots: Mapping[str, ET.Element]
) -> tuple[GameClass, ...]:
    """Build every class whose chapter is present in `chapters`.

    Only chapters in `CLASS_CHAPTER_IDS` are built, in that tuple's order (the real
    manifest always contains all eight, in book order; synthetic manifests may
    contain just one).
    """
    chapter_ids = {chapter.id for chapter in chapters}
    present = [class_id for class_id in CLASS_CHAPTER_IDS if class_id in chapter_ids]
    return tuple(
        extract_class(
            next(chapter for chapter in chapters if chapter.id == class_id),
            roots[class_id],
            order,
        )
        for order, class_id in enumerate(present)
    )

"""Splits one parsed chapter file into chapter / h1 / h2 sections (D4, D5).

Each file's element tree is flattened into a document-order sequence of loose text,
content blocks and ``h1``/``h2`` headings (``Root``, ``Body``, ``Story`` and ``div`` are
transparent containers - see docs/source-notes.md). Headings start new sections;
everything else is rendered into the active section's ``text_markdown``.
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterator

from ingestion.manifest import Chapter
from ingestion.markdown import UnknownMarkup, plain_text, render_block, slugify
from ingestion.models import Section

_CONTAINER_TAGS = frozenset({"Root", "Body", "Story", "div"})
_HEADING_TAGS = frozenset({"h1", "h2"})
_HEADING_LIKE_TAGS = frozenset({"h1", "h2", "h3", "h4"})

FlatItem = ET.Element | str


def flatten_items(container: ET.Element) -> Iterator[FlatItem]:
    """Yield `container`'s content in document order, descending transparently.

    Non-whitespace text directly inside a container (its own leading text, or a
    child's tail) is yielded as a loose string; every other child is either a
    transparent container (descended into) or a block/heading element. Shared with
    `ingestion/moves.py`, which walks the same sequence to find move headings and
    their enclosing `h1`.
    """
    if container.text and container.text.strip():
        yield container.text
    for child in container:
        if child.tag in _CONTAINER_TAGS:
            yield from flatten_items(child)
        else:
            yield child
        if child.tail and child.tail.strip():
            yield child.tail


class _SectionBuilder:
    """Mutable accumulator for one section's content while a chapter is walked."""

    __slots__ = ("blocks", "chapter", "id", "order", "parent_id", "slug", "title")

    def __init__(
        self,
        id: str,
        chapter: str,
        title: str,
        slug: str,
        parent_id: str | None,
        order: int,
    ) -> None:
        self.id = id
        self.chapter = chapter
        self.title = title
        self.slug = slug
        self.parent_id = parent_id
        self.order = order
        self.blocks: list[str] = []

    def finalize(self) -> Section:
        return Section(
            id=self.id,
            chapter=self.chapter,
            title=self.title,
            slug=self.slug,
            parent_id=self.parent_id,
            order=self.order,
            text_markdown="\n\n".join(block for block in self.blocks if block),
        )


def _find_chapter_heading(
    flat_items: list[FlatItem], chapter: Chapter
) -> ET.Element | None:
    """Return the first `h1`-`h4` element if it is a matching `h1`, else None."""
    for item in flat_items:
        if isinstance(item, str) or item.tag not in _HEADING_LIKE_TAGS:
            continue
        if item.tag == "h1" and plain_text(item).casefold() == chapter.title.casefold():
            return item
        return None
    return None


def build_chapter_sections(
    chapter: Chapter,
    root: ET.Element,
    unknown: UnknownMarkup,
    file: str,
    start_order: int,
) -> tuple[tuple[Section, ...], int]:
    """Build every section of one chapter, starting ids at `start_order`.

    Returns the chapter's sections (the chapter section first, then its descendants in
    document order) and the next available global order value.
    """
    flat_items = list(flatten_items(root))
    consumed_heading = _find_chapter_heading(flat_items, chapter)

    order = start_order
    chapter_builder = _SectionBuilder(
        id=chapter.id,
        chapter=chapter.id,
        title=chapter.title,
        slug=chapter.id,
        parent_id=None,
        order=order,
    )
    order += 1
    builders = [chapter_builder]
    current = chapter_builder
    last_h1_id: str | None = None
    slug_counts: dict[str, int] = {}

    for item in flat_items:
        if item is consumed_heading:
            continue
        if isinstance(item, ET.Element) and item.tag in _HEADING_TAGS:
            title = plain_text(item)
            base_slug = slugify(title) or f"section-{order}"
            slug_counts[base_slug] = slug_counts.get(base_slug, 0) + 1
            count = slug_counts[base_slug]
            slug = base_slug if count == 1 else f"{base_slug}-{count}"
            section_id = f"{chapter.id}/{slug}"
            if item.tag == "h1":
                parent_id = chapter.id
            else:
                parent_id = last_h1_id if last_h1_id is not None else chapter.id
            builder = _SectionBuilder(
                id=section_id,
                chapter=chapter.id,
                title=title,
                slug=slug,
                parent_id=parent_id,
                order=order,
            )
            order += 1
            builders.append(builder)
            current = builder
            if item.tag == "h1":
                last_h1_id = section_id
            continue

        rendered = render_block(item, unknown, file)
        if rendered:
            current.blocks.append(rendered)

    return tuple(builder.finalize() for builder in builders), order

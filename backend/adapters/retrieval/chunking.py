"""Section/move chunking for the retrieval index (spec 007 D8, D9, D10).

Pure functions over spec 005's `Section`/`Move` domain types: no I/O, no embedding.
`build_chunks` turns the normalized rulebook into the semantic units the hybrid
retriever indexes, and `chunks_to_json` is the single deterministic serialiser shared
by the index build CLI (story 3) and the freshness test.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from backend.domain.rulebook import SECTION_ID, SLUG, Move, Section
from backend.domain.urls import section_url
from backend.ports.retriever import ChunkType

MAX_CHUNK_CHARS: Final = 6000
EMBED_MAX_CHARS: Final = 24000
EXCLUDED_CHAPTERS: Final[frozenset[str]] = frozenset({"thanks"})

_BLOCK_SPLIT = re.compile(r"\n\s*\n")


@dataclass(frozen=True, slots=True)
class IndexChunk:
    chunk_id: str
    section_id: str
    title: str
    chapter: str
    anchor_url: str
    type: ChunkType
    part: int
    parts: int
    text: str
    index_text: str

    def __post_init__(self) -> None:
        ref = self.chunk_id or self.section_id or "?"
        for field_name, value in (
            ("chunk_id", self.chunk_id),
            ("section_id", self.section_id),
            ("title", self.title),
            ("chapter", self.chapter),
            ("text", self.text),
            ("index_text", self.index_text),
        ):
            if not value.strip():
                raise ValueError(
                    f"invalid IndexChunk {ref!r}: {field_name} must be non-empty"
                )
        if not SECTION_ID.fullmatch(self.section_id):
            raise ValueError(
                f"invalid IndexChunk {ref!r}: section_id must match "
                f"{SECTION_ID.pattern!r}"
            )
        if not SLUG.fullmatch(self.chapter):
            raise ValueError(
                f"invalid IndexChunk {ref!r}: chapter must match {SLUG.pattern!r}"
            )
        if self.type not in ("section", "move"):
            raise ValueError(
                f"invalid IndexChunk {ref!r}: type must be 'section' or 'move'"
            )
        if isinstance(self.part, bool):
            raise ValueError(f"invalid IndexChunk {ref!r}: part must be int, not bool")
        if isinstance(self.parts, bool):
            raise ValueError(f"invalid IndexChunk {ref!r}: parts must be int, not bool")
        if not (1 <= self.part <= self.parts):
            raise ValueError(
                f"invalid IndexChunk {ref!r}: must have 1 <= part <= parts"
            )
        if self.type == "move" and self.parts != 1:
            raise ValueError(
                f"invalid IndexChunk {ref!r}: a move chunk must have parts == 1"
            )
        expected_id = (
            self.section_id if self.parts == 1 else f"{self.section_id}#{self.part}"
        )
        if self.chunk_id != expected_id:
            raise ValueError(
                f"invalid IndexChunk {ref!r}: chunk_id must equal {expected_id!r}"
            )
        expected_url = section_url(self.section_id)
        if self.anchor_url != expected_url:
            raise ValueError(
                f"invalid IndexChunk {ref!r}: anchor_url must equal {expected_url!r}"
            )


def _pack_blocks(blocks: Sequence[str]) -> list[str]:
    """Greedily pack blocks into parts, never splitting a block (D8c)."""
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in blocks:
        if not current:
            current = [block]
            current_len = len(block)
            continue
        candidate_len = current_len + 2 + len(block)
        if candidate_len <= MAX_CHUNK_CHARS:
            current.append(block)
            current_len = candidate_len
        else:
            parts.append("\n\n".join(current))
            current = [block]
            current_len = len(block)
    if current:
        parts.append("\n\n".join(current))
    return parts


def _section_parts(text: str) -> list[str]:
    """The one or more parts a section's stripped text splits into (D8c)."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    blocks = [block.strip() for block in _BLOCK_SPLIT.split(text) if block.strip()]
    return _pack_blocks(blocks)


def _index_text(
    section: Section, chapter_title: Mapping[str, str], title: str, text: str
) -> str:
    """D10: chapter-qualified header over the chunk's own title, plus the text."""
    if section.id == section.chapter:
        header = title
    else:
        header = f"{chapter_title[section.chapter]} > {title}"
    return f"{header}\n\n{text}"


def _move_chunk(
    section: Section, move: Move, chapter_title: Mapping[str, str]
) -> IndexChunk:
    text = move.body_markdown.strip()
    return IndexChunk(
        chunk_id=section.id,
        section_id=section.id,
        title=move.name,
        chapter=section.chapter,
        anchor_url=section_url(section.id),
        type="move",
        part=1,
        parts=1,
        text=text,
        index_text=_index_text(section, chapter_title, move.name, text),
    )


def _section_chunks(
    section: Section, text: str, chapter_title: Mapping[str, str]
) -> list[IndexChunk]:
    parts = _section_parts(text)
    total = len(parts)
    chunks: list[IndexChunk] = []
    for position, part_text in enumerate(parts, start=1):
        chunk_id = section.id if total == 1 else f"{section.id}#{position}"
        chunks.append(
            IndexChunk(
                chunk_id=chunk_id,
                section_id=section.id,
                title=section.title,
                chapter=section.chapter,
                anchor_url=section_url(section.id),
                type="section",
                part=position,
                parts=total,
                text=part_text,
                index_text=_index_text(
                    section, chapter_title, section.title, part_text
                ),
            )
        )
    return chunks


def build_chunks(
    sections: Sequence[Section], moves: Sequence[Move]
) -> tuple[IndexChunk, ...]:
    move_by_section = {move.section_id: move for move in moves}
    chapter_title = {s.chapter: s.title for s in sections if s.id == s.chapter}

    section_ids = {s.id for s in sections}
    missing = sorted({move.section_id for move in moves} - section_ids)
    if missing:
        raise ValueError(f"move section_id(s) not found in sections: {missing!r}")

    chunks: list[IndexChunk] = []
    for section in sections:
        if section.chapter in EXCLUDED_CHAPTERS:
            continue
        move = move_by_section.get(section.id)
        if move is not None:
            chunks.append(_move_chunk(section, move, chapter_title))
            continue
        text = section.text_markdown.strip()
        if not text:
            continue
        chunks.extend(_section_chunks(section, text, chapter_title))
    return tuple(chunks)


def chunks_to_json(chunks: Sequence[IndexChunk]) -> str:
    rows = [
        {
            "chunk_id": chunk.chunk_id,
            "section_id": chunk.section_id,
            "title": chunk.title,
            "chapter": chunk.chapter,
            "anchor_url": chunk.anchor_url,
            "type": chunk.type,
            "part": chunk.part,
            "parts": chunk.parts,
            "text": chunk.text,
            "index_text": chunk.index_text,
        }
        for chunk in chunks
    ]
    return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"

"""Tests for section/move chunking (spec 007 Testing)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.adapters.retrieval.chunking import (
    MAX_CHUNK_CHARS,
    IndexChunk,
    build_chunks,
    chunks_to_json,
)
from backend.domain.rulebook import Move, Section, move_from_dict, section_from_dict
from backend.tests.adapter_helpers import mini_normalized
from backend.tests.domain_helpers import HACK_AND_SLASH

_COMMITTED_SECTIONS = Path("data/normalized/sections.json")
_COMMITTED_MOVES = Path("data/normalized/moves.json")


def _load_normalized(directory: Path) -> tuple[list[Section], list[Move]]:
    sections_raw = json.loads((directory / "sections.json").read_text("utf-8"))
    moves_raw = json.loads((directory / "moves.json").read_text("utf-8"))
    sections = [section_from_dict(item) for item in sections_raw]
    moves = [move_from_dict(item) for item in moves_raw]
    return sections, moves


def test_move_section_replaced_by_move_chunk(tmp_path: Path) -> None:
    sections, moves = _load_normalized(mini_normalized(tmp_path))

    chunks = build_chunks(sections, moves)

    matches = [c for c in chunks if c.section_id == "moves/hack-and-slash"]
    assert len(matches) == 1
    chunk = matches[0]
    assert chunk.type == "move"
    assert chunk.title == "Hack and Slash"
    assert chunk.text == str(HACK_AND_SLASH["body_markdown"]).strip()


def test_thanks_chapter_excluded(tmp_path: Path) -> None:
    sections, moves = _load_normalized(mini_normalized(tmp_path))

    chunks = build_chunks(sections, moves)

    assert all(c.chapter != "thanks" for c in chunks)


def test_empty_sections_skipped(tmp_path: Path) -> None:
    sections, moves = _load_normalized(mini_normalized(tmp_path))

    chunks = build_chunks(sections, moves)

    assert all(c.section_id != "moves/empty" for c in chunks)


def test_oversized_section_split_on_block_boundaries(tmp_path: Path) -> None:
    sections, moves = _load_normalized(mini_normalized(tmp_path))
    section = next(s for s in sections if s.id == "gm/big-section")

    chunks = [c for c in build_chunks(sections, moves) if c.section_id == section.id]

    assert len(chunks) == 3
    assert [c.chunk_id for c in chunks] == [
        "gm/big-section#1",
        "gm/big-section#2",
        "gm/big-section#3",
    ]
    for chunk in chunks:
        assert chunk.section_id == section.id
        assert chunk.title == section.title
        assert chunk.anchor_url == "/rules/gm/big-section/"
        assert len(chunk.text) <= MAX_CHUNK_CHARS

    expected_blocks = [
        block.strip()
        for block in section.text_markdown.strip().split("\n\n")
        if block.strip()
    ]
    assert "\n\n".join(c.text for c in chunks) == "\n\n".join(expected_blocks)


def test_single_huge_block_kept_whole(tmp_path: Path) -> None:
    sections, moves = _load_normalized(mini_normalized(tmp_path))

    chunks = [
        c for c in build_chunks(sections, moves) if c.section_id == "gm/huge-block"
    ]

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.parts == 1
    assert chunk.chunk_id == "gm/huge-block"
    assert len(chunk.text) == 7000


def test_moves_never_split(tmp_path: Path) -> None:
    normalized_dir = mini_normalized(tmp_path)
    sections_raw = json.loads((normalized_dir / "sections.json").read_text("utf-8"))
    moves_raw = json.loads((normalized_dir / "moves.json").read_text("utf-8"))

    huge_body = "z" * 7000
    for section in sections_raw:
        if section["id"] == "moves/hack-and-slash":
            section["text_markdown"] = huge_body
    for move in moves_raw:
        if move["id"] == "hack-and-slash":
            move["body_markdown"] = huge_body

    sections = [section_from_dict(item) for item in sections_raw]
    moves = [move_from_dict(item) for item in moves_raw]

    chunks = [
        c
        for c in build_chunks(sections, moves)
        if c.section_id == "moves/hack-and-slash"
    ]

    assert len(chunks) == 1
    assert chunks[0].type == "move"
    assert chunks[0].parts == 1
    assert chunks[0].text == huge_body


def test_anchor_url_matches_url_contract(tmp_path: Path) -> None:
    sections, moves = _load_normalized(mini_normalized(tmp_path))

    chunks = build_chunks(sections, moves)

    assert chunks
    for chunk in chunks:
        assert chunk.anchor_url == f"/rules/{chunk.section_id}/"


def test_index_text_header(tmp_path: Path) -> None:
    sections, moves = _load_normalized(mini_normalized(tmp_path))
    chunks = build_chunks(sections, moves)

    child = next(c for c in chunks if c.section_id == "gm/huge-block")
    assert child.index_text == f"The GM > Huge Block\n\n{child.text}"

    root = next(c for c in chunks if c.section_id == "gm")
    assert root.index_text == f"The GM\n\n{root.text}"


def test_build_chunks_deterministic(tmp_path: Path) -> None:
    sections, moves = _load_normalized(mini_normalized(tmp_path))

    first = chunks_to_json(build_chunks(sections, moves))
    second = chunks_to_json(build_chunks(sections, moves))

    assert first == second


def test_committed_data_chunks_valid() -> None:
    if not _COMMITTED_SECTIONS.exists():
        pytest.skip("data/normalized not built yet")

    sections = [
        section_from_dict(item)
        for item in json.loads(_COMMITTED_SECTIONS.read_text("utf-8"))
    ]
    moves = [
        move_from_dict(item) for item in json.loads(_COMMITTED_MOVES.read_text("utf-8"))
    ]

    chunks = build_chunks(sections, moves)

    move_chunks = [c for c in chunks if c.type == "move"]
    assert len(move_chunks) == 21

    chunk_ids = [c.chunk_id for c in chunks]
    assert len(chunk_ids) == len(set(chunk_ids))

    assert all(c.chapter != "thanks" for c in chunks)

    move_section_ids = {m.section_id for m in moves}
    assert not any(
        c.type == "section" and c.section_id in move_section_ids for c in chunks
    )


def test_index_chunk_rejects_bad_part_parts() -> None:
    with pytest.raises(ValueError, match="part"):
        IndexChunk(
            chunk_id="gm",
            section_id="gm",
            title="The GM",
            chapter="gm",
            anchor_url="/rules/gm/",
            type="section",
            part=2,
            parts=1,
            text="text",
            index_text="The GM\n\ntext",
        )

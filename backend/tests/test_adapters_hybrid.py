"""Tests for the hybrid (vector + BM25) retriever (spec 007 Testing)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from backend.adapters.retrieval.chunking import IndexChunk, build_chunks, chunks_to_json
from backend.adapters.retrieval.hybrid import HybridRetriever
from backend.adapters.retrieval.index import (
    IndexManifest,
    LoadedIndex,
    load_index,
    write_index,
)
from backend.domain.rulebook import Move, Section, move_from_dict, section_from_dict
from backend.domain.urls import section_url
from backend.ports.errors import PortError
from backend.ports.retriever import Retriever
from backend.tests.adapter_helpers import (
    ScriptedEmbedder,
    VectorStubEmbedder,
    mini_normalized,
)
from backend.tests.fakes.embedder import FakeEmbedder


def _load_normalized(normalized_dir: Path) -> tuple[list[Section], list[Move]]:
    sections_raw = json.loads(
        (normalized_dir / "sections.json").read_text(encoding="utf-8")
    )
    moves_raw = json.loads((normalized_dir / "moves.json").read_text(encoding="utf-8"))
    sections = [section_from_dict(item) for item in sections_raw]
    moves = [move_from_dict(item) for item in moves_raw]
    return sections, moves


def _write_mini_index(tmp_path: Path) -> Path:
    normalized_dir = mini_normalized(tmp_path)
    sections, moves = _load_normalized(normalized_dir)
    chunks = build_chunks(sections, moves)
    embedder = FakeEmbedder(dim=64)
    vectors = asyncio.run(embedder.embed([chunk.index_text for chunk in chunks]))
    out_dir = tmp_path / "index"
    write_index(out_dir, chunks, vectors, "fake-embed")
    return out_dir


def test_returns_at_most_k_distinct_sections(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    retriever = HybridRetriever(load_index(index_dir), FakeEmbedder(dim=64))

    results = asyncio.run(retriever.retrieve("the", k=3))

    assert len(results) <= 3
    assert len({result.section_id for result in results}) == len(results)


def test_split_section_appears_once(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    loaded = load_index(index_dir)
    expected_text = next(
        chunk.text for chunk in loaded.chunks if chunk.chunk_id == "gm/big-section#2"
    )
    retriever = HybridRetriever(loaded, FakeEmbedder(dim=64))

    results = asyncio.run(retriever.retrieve("Block 5", k=5))

    matches = [result for result in results if result.section_id == "gm/big-section"]
    assert len(matches) == 1
    assert matches[0].text == expected_text


def test_bm25_rescues_exact_term(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    loaded = load_index(index_dir)
    volley_row = next(
        loaded.embeddings[i]
        for i, chunk in enumerate(loaded.chunks)
        if chunk.section_id == "moves/volley"
    )
    embedder = VectorStubEmbedder(index_dir, {"last breath": volley_row.tolist()})
    retriever = HybridRetriever(loaded, embedder)

    results = asyncio.run(retriever.retrieve("last breath", k=5))

    section_ids = [result.section_id for result in results]
    assert "moves/last-breath" in section_ids
    assert "moves/volley" in section_ids
    assert section_ids.index("moves/last-breath") < section_ids.index("moves/volley")


def test_rrf_order() -> None:
    chunk_a = IndexChunk(
        chunk_id="gm",
        section_id="gm",
        title="GM",
        chapter="gm",
        anchor_url=section_url("gm"),
        type="section",
        part=1,
        parts=1,
        text="A body text.",
        index_text="GM\n\nzoo alpha beta gamma delta",
    )
    chunk_b = IndexChunk(
        chunk_id="moves",
        section_id="moves",
        title="Moves",
        chapter="moves",
        anchor_url=section_url("moves"),
        type="section",
        part=1,
        parts=1,
        text="B body text.",
        index_text="Moves\n\nzoo zoo",
    )
    chunks_json = chunks_to_json([chunk_a, chunk_b])
    manifest = IndexManifest(
        format_version=1,
        embedding_model="scripted",
        dimensions=2,
        chunk_count=2,
        chunks_sha256=hashlib.sha256(chunks_json.encode("utf-8")).hexdigest(),
    )
    embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    loaded = LoadedIndex(
        manifest=manifest, chunks=(chunk_a, chunk_b), embeddings=embeddings
    )
    embedder = ScriptedEmbedder({"zoo": [1.0, 0.0]})
    retriever = HybridRetriever(loaded, embedder)

    results = asyncio.run(retriever.retrieve("zoo", k=2))

    expected_score = 1.0 / 61.0 + 1.0 / 62.0
    assert [result.section_id for result in results] == ["gm", "moves"]
    assert results[0].score == pytest.approx(expected_score)
    assert results[1].score == pytest.approx(expected_score)
    assert results[0].score == results[1].score


def test_empty_query_no_embedding_call(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    embedder = FakeEmbedder(dim=64)
    retriever = HybridRetriever(load_index(index_dir), embedder)

    results = asyncio.run(retriever.retrieve("  ", k=3))

    assert results == []
    assert embedder.calls == []


def test_embedder_error_is_port_error(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    embedder = FakeEmbedder(dim=64, error=PortError("down"))
    retriever = HybridRetriever(load_index(index_dir), embedder)

    with pytest.raises(PortError):
        asyncio.run(retriever.retrieve("hack and slash", k=3))


def test_zero_norm_query_raises_port_error(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    embedder = ScriptedEmbedder({"query": [0.0] * 64})
    retriever = HybridRetriever(load_index(index_dir), embedder)

    with pytest.raises(PortError, match="zero vector"):
        asyncio.run(retriever.retrieve("query", k=3))


def test_k_must_be_positive(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    retriever = HybridRetriever(load_index(index_dir), FakeEmbedder(dim=64))

    with pytest.raises(ValueError, match="k"):
        asyncio.run(retriever.retrieve("hack and slash", k=0))


def test_results_are_valid_retrieved_chunks(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    retriever = HybridRetriever(load_index(index_dir), FakeEmbedder(dim=64))

    results = asyncio.run(retriever.retrieve("hack and slash the gm", k=6))

    assert results
    for result in results:
        assert result.type in ("section", "move")
        assert result.anchor_url == section_url(result.section_id)
        assert math.isfinite(result.score)
    scores = [result.score for result in results]
    assert scores == sorted(scores, reverse=True)


def test_satisfies_retriever_protocol(tmp_path: Path) -> None:
    index_dir = _write_mini_index(tmp_path)
    retriever: Retriever = HybridRetriever(load_index(index_dir), FakeEmbedder(dim=64))

    assert isinstance(retriever, HybridRetriever)

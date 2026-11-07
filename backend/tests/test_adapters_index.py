"""Tests for the index artifact and the build CLI (spec 007 Testing)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest

from backend.adapters.retrieval import build
from backend.adapters.retrieval.chunking import IndexChunk, build_chunks, chunks_to_json
from backend.adapters.retrieval.embedder import Embedder
from backend.adapters.retrieval.index import load_index, write_index
from backend.domain.rulebook import Move, Section, move_from_dict, section_from_dict
from backend.ports.errors import PortError
from backend.tests.adapter_helpers import mini_normalized
from backend.tests.fakes.embedder import FakeEmbedder


def _make_fake_embedder(api_key: str, model: str) -> Embedder:
    return FakeEmbedder()


def _make_failing_embedder(api_key: str, model: str) -> Embedder:
    return FakeEmbedder(error=PortError("down"))


_COMMITTED_NORMALIZED_DIR = Path("data/normalized")
_COMMITTED_INDEX_DIR = Path("data/index")


def _load_normalized(normalized_dir: Path) -> tuple[list[Section], list[Move]]:
    sections_raw = json.loads(
        (normalized_dir / "sections.json").read_text(encoding="utf-8")
    )
    moves_raw = json.loads((normalized_dir / "moves.json").read_text(encoding="utf-8"))
    sections = [section_from_dict(item) for item in sections_raw]
    moves = [move_from_dict(item) for item in moves_raw]
    return sections, moves


def _mini_chunks(tmp_path: Path) -> tuple[IndexChunk, ...]:
    normalized_dir = mini_normalized(tmp_path)
    sections, moves = _load_normalized(normalized_dir)
    return build_chunks(sections, moves)


def _write_mini_index(tmp_path: Path) -> tuple[Path, tuple[IndexChunk, ...]]:
    chunks = _mini_chunks(tmp_path)
    embedder = FakeEmbedder(dim=64)
    vectors = asyncio.run(embedder.embed([chunk.index_text for chunk in chunks]))
    out_dir = tmp_path / "index"
    write_index(out_dir, chunks, vectors, "fake-embed")
    return out_dir, chunks


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    out_dir, chunks = _write_mini_index(tmp_path)

    loaded = load_index(out_dir)

    assert loaded.chunks == chunks
    assert loaded.embeddings.dtype == np.float32
    assert loaded.embeddings.shape == (len(chunks), 64)
    norms = np.linalg.norm(loaded.embeddings, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)
    assert loaded.manifest.embedding_model == "fake-embed"
    chunks_json = chunks_to_json(chunks)
    assert (out_dir / "chunks.json").read_text(encoding="utf-8") == chunks_json
    assert loaded.manifest.chunk_count == len(chunks)


def test_load_rejects_tampered_chunks(tmp_path: Path) -> None:
    out_dir, _chunks = _write_mini_index(tmp_path)

    chunks_path = out_dir / "chunks.json"
    text = chunks_path.read_text(encoding="utf-8")
    assert text.endswith("]\n")
    tampered = text[:-2] + "X" + text[-1]
    chunks_path.write_text(tampered, encoding="utf-8")

    with pytest.raises(ValueError, match="chunks_sha256"):
        load_index(out_dir)


def test_load_rejects_shape_mismatch(tmp_path: Path) -> None:
    out_dir, _chunks = _write_mini_index(tmp_path)

    embeddings_path = out_dir / "embeddings.npy"
    matrix = np.load(embeddings_path)
    np.save(embeddings_path, matrix[:-1], allow_pickle=False)

    with pytest.raises(ValueError, match="shape"):
        load_index(out_dir)


def test_load_rejects_non_finite(tmp_path: Path) -> None:
    out_dir, _chunks = _write_mini_index(tmp_path)

    embeddings_path = out_dir / "embeddings.npy"
    matrix = np.load(embeddings_path)
    matrix[0, 0] = np.nan
    np.save(embeddings_path, matrix, allow_pickle=False)

    with pytest.raises(ValueError, match="finite"):
        load_index(out_dir)


def test_load_rejects_pickled_array(tmp_path: Path) -> None:
    out_dir, chunks = _write_mini_index(tmp_path)

    embeddings_path = out_dir / "embeddings.npy"
    object_array = np.array([object()] * len(chunks), dtype=object)
    np.save(embeddings_path, object_array, allow_pickle=True)

    with pytest.raises(ValueError, match="allow_pickle"):
        load_index(out_dir)


def test_load_missing_file(tmp_path: Path) -> None:
    out_dir, _chunks = _write_mini_index(tmp_path)

    (out_dir / "manifest.json").unlink()

    with pytest.raises(FileNotFoundError):
        load_index(out_dir)


def test_write_rejects_zero_vector(tmp_path: Path) -> None:
    chunks = _mini_chunks(tmp_path)
    vectors = [[0.0] * 64 for _ in chunks]

    with pytest.raises(ValueError, match="zero vector"):
        write_index(tmp_path / "index", chunks, vectors, "fake-embed")


def test_build_cli_writes_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    normalized_dir = mini_normalized(tmp_path)
    out_dir = tmp_path / "index"
    monkeypatch.setattr(build, "make_embedder", _make_fake_embedder)

    code = build.main(
        ["--normalized", str(normalized_dir), "--out", str(out_dir)],
        environ={"OPENROUTER_API_KEY": "key", "MODEL_EMBEDDINGS": "fake-embed"},
    )

    assert code == 0
    assert (out_dir / "manifest.json").is_file()
    assert (out_dir / "chunks.json").is_file()
    assert (out_dir / "embeddings.npy").is_file()
    captured = capsys.readouterr()
    assert captured.out.startswith("index-build: ")
    assert "chunks" in captured.out
    assert "dims" in captured.out
    assert "model fake-embed" in captured.out


def test_build_cli_missing_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    normalized_dir = mini_normalized(tmp_path)
    out_dir = tmp_path / "index"

    code = build.main(
        ["--normalized", str(normalized_dir), "--out", str(out_dir)],
        environ={"MODEL_EMBEDDINGS": "fake-embed"},
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "OPENROUTER_API_KEY is required" in captured.err
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_build_cli_provider_failure_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    normalized_dir = mini_normalized(tmp_path)
    out_dir = tmp_path / "index"
    monkeypatch.setattr(build, "make_embedder", _make_failing_embedder)

    code = build.main(
        ["--normalized", str(normalized_dir), "--out", str(out_dir)],
        environ={"OPENROUTER_API_KEY": "key", "MODEL_EMBEDDINGS": "fake-embed"},
    )

    assert code == 2
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_committed_index_is_fresh() -> None:
    if not (_COMMITTED_INDEX_DIR / "manifest.json").exists():
        pytest.skip(
            "data/index not committed yet: run "
            "python -m backend.adapters.retrieval.build with OPENROUTER_API_KEY"
        )

    sections, moves = _load_normalized(_COMMITTED_NORMALIZED_DIR)
    chunks = build_chunks(sections, moves)

    committed_chunks_json = (_COMMITTED_INDEX_DIR / "chunks.json").read_text(
        encoding="utf-8"
    )
    assert chunks_to_json(chunks) == committed_chunks_json

    load_index(_COMMITTED_INDEX_DIR)

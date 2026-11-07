"""The on-disk index artifact: manifest, chunk array and embedding matrix (D2-D4).

`write_index` is the only way the three files are produced (by the build CLI,
`retrieval/build.py`). `load_index` performs the seven ordered checks from the spec
before trusting anything on disk (Authorization & Security: untrusted artifact
loading, `np.load(..., allow_pickle=False)`).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

import numpy as np
from numpy.typing import NDArray

from backend.adapters.retrieval.chunking import IndexChunk, chunks_to_json

FORMAT_VERSION: Final = 1

_MANIFEST_FILE = "manifest.json"
_CHUNKS_FILE = "chunks.json"
_EMBEDDINGS_FILE = "embeddings.npy"

_MANIFEST_KEYS: Final[frozenset[str]] = frozenset(
    {"format_version", "embedding_model", "dimensions", "chunk_count", "chunks_sha256"}
)
_CHUNK_KEYS: Final[frozenset[str]] = frozenset(
    {
        "chunk_id",
        "section_id",
        "title",
        "chapter",
        "anchor_url",
        "type",
        "part",
        "parts",
        "text",
        "index_text",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NORM_TOLERANCE: Final = 1e-3


@dataclass(frozen=True, slots=True)
class IndexManifest:
    format_version: int
    embedding_model: str
    dimensions: int
    chunk_count: int
    chunks_sha256: str

    def __post_init__(self) -> None:
        if self.format_version != FORMAT_VERSION:
            raise ValueError(
                f"invalid IndexManifest: format_version must be {FORMAT_VERSION}"
            )
        if not self.embedding_model.strip():
            raise ValueError("invalid IndexManifest: embedding_model must be non-empty")
        if isinstance(self.dimensions, bool) or self.dimensions < 1:
            raise ValueError("invalid IndexManifest: dimensions must be an int >= 1")
        if isinstance(self.chunk_count, bool) or self.chunk_count < 1:
            raise ValueError("invalid IndexManifest: chunk_count must be an int >= 1")
        if not _SHA256_RE.fullmatch(self.chunks_sha256):
            raise ValueError(
                "invalid IndexManifest: chunks_sha256 must match "
                f"{_SHA256_RE.pattern!r}"
            )


@dataclass(frozen=True, slots=True)
class LoadedIndex:
    manifest: IndexManifest
    chunks: tuple[IndexChunk, ...]
    embeddings: NDArray[np.float32] = field(compare=False)


def write_index(
    out_dir: Path,
    chunks: Sequence[IndexChunk],
    vectors: Sequence[Sequence[float]],
    embedding_model: str,
) -> IndexManifest:
    if len(vectors) != len(chunks):
        raise ValueError(
            "invalid write_index: vectors and chunks must have the same length"
        )
    if not chunks:
        raise ValueError("invalid write_index: chunks must be non-empty")

    dimensions = len(vectors[0])
    if dimensions == 0:
        raise ValueError("invalid write_index: vectors must have a non-zero dimension")

    matrix = np.empty((len(vectors), dimensions), dtype=np.float32)
    for row, vector in enumerate(vectors):
        if len(vector) != dimensions:
            raise ValueError(
                "invalid write_index: all vectors must have the same dimension"
            )
        values = np.asarray(vector, dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise ValueError(f"invalid write_index: vector {row} is not finite")
        norm = float(np.linalg.norm(values))
        if norm == 0.0:
            raise ValueError(f"invalid write_index: vector {row} is a zero vector")
        matrix[row] = (values / norm).astype(np.float32)

    chunks_json = chunks_to_json(chunks)
    chunks_sha256 = hashlib.sha256(chunks_json.encode("utf-8")).hexdigest()
    manifest = IndexManifest(
        format_version=FORMAT_VERSION,
        embedding_model=embedding_model,
        dimensions=dimensions,
        chunk_count=len(chunks),
        chunks_sha256=chunks_sha256,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_json = (
        json.dumps(
            {
                "format_version": manifest.format_version,
                "embedding_model": manifest.embedding_model,
                "dimensions": manifest.dimensions,
                "chunk_count": manifest.chunk_count,
                "chunks_sha256": manifest.chunks_sha256,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    (out_dir / _MANIFEST_FILE).write_text(manifest_json, encoding="utf-8")
    (out_dir / _CHUNKS_FILE).write_text(chunks_json, encoding="utf-8")
    np.save(out_dir / _EMBEDDINGS_FILE, matrix, allow_pickle=False)
    return manifest


def _parse_manifest(data: Mapping[str, object], path: Path) -> IndexManifest:
    keys = frozenset(data.keys())
    if keys != _MANIFEST_KEYS:
        raise ValueError(
            f"invalid {path}: must have exactly keys {sorted(_MANIFEST_KEYS)}"
        )

    format_version = data["format_version"]
    if isinstance(format_version, bool) or not isinstance(format_version, int):
        raise ValueError(f"invalid {path}: format_version must be int")

    embedding_model = data["embedding_model"]
    if not isinstance(embedding_model, str):
        raise ValueError(f"invalid {path}: embedding_model must be str")

    dimensions = data["dimensions"]
    if isinstance(dimensions, bool) or not isinstance(dimensions, int):
        raise ValueError(f"invalid {path}: dimensions must be int")

    chunk_count = data["chunk_count"]
    if isinstance(chunk_count, bool) or not isinstance(chunk_count, int):
        raise ValueError(f"invalid {path}: chunk_count must be int")

    chunks_sha256 = data["chunks_sha256"]
    if not isinstance(chunks_sha256, str):
        raise ValueError(f"invalid {path}: chunks_sha256 must be str")

    try:
        return IndexManifest(
            format_version=format_version,
            embedding_model=embedding_model,
            dimensions=dimensions,
            chunk_count=chunk_count,
            chunks_sha256=chunks_sha256,
        )
    except ValueError as exc:
        raise ValueError(f"invalid {path}: {exc}") from exc


def _str_field(data: Mapping[str, object], key: str, path: Path) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"invalid {path}: {key} must be str")
    return value


def _int_field(data: Mapping[str, object], key: str, path: Path) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid {path}: {key} must be int")
    return value


def _parse_chunk(data: object, path: Path) -> IndexChunk:
    if not isinstance(data, dict):
        raise ValueError(f"invalid {path}: each chunk must be a JSON object")
    raw = cast(Mapping[str, object], data)
    keys = frozenset(raw.keys())
    if keys != _CHUNK_KEYS:
        raise ValueError(
            f"invalid {path}: each chunk must have exactly keys {sorted(_CHUNK_KEYS)}"
        )

    chunk_type = _str_field(raw, "type", path)
    if chunk_type not in ("section", "move"):
        raise ValueError(f"invalid {path}: type must be 'section' or 'move'")

    try:
        return IndexChunk(
            chunk_id=_str_field(raw, "chunk_id", path),
            section_id=_str_field(raw, "section_id", path),
            title=_str_field(raw, "title", path),
            chapter=_str_field(raw, "chapter", path),
            anchor_url=_str_field(raw, "anchor_url", path),
            type=chunk_type,
            part=_int_field(raw, "part", path),
            parts=_int_field(raw, "parts", path),
            text=_str_field(raw, "text", path),
            index_text=_str_field(raw, "index_text", path),
        )
    except ValueError as exc:
        raise ValueError(f"invalid {path}: {exc}") from exc


def load_index(index_dir: Path) -> LoadedIndex:
    manifest_path = index_dir / _MANIFEST_FILE
    chunks_path = index_dir / _CHUNKS_FILE
    embeddings_path = index_dir / _EMBEDDINGS_FILE

    for path in (manifest_path, chunks_path, embeddings_path):
        if not path.is_file():
            raise FileNotFoundError(f"missing index file: {path}")

    manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest_raw, dict):
        raise ValueError(f"invalid {manifest_path}: must be a JSON object")
    manifest = _parse_manifest(cast(Mapping[str, object], manifest_raw), manifest_path)

    chunks_bytes = chunks_path.read_bytes()
    actual_sha256 = hashlib.sha256(chunks_bytes).hexdigest()
    if actual_sha256 != manifest.chunks_sha256:
        raise ValueError(
            f"invalid {chunks_path}: sha256 does not match manifest chunks_sha256"
        )

    chunks_parsed = json.loads(chunks_bytes.decode("utf-8"))
    if not isinstance(chunks_parsed, list):
        raise ValueError(f"invalid {chunks_path}: must be a JSON array")
    chunks_raw = cast(list[object], chunks_parsed)
    chunks = tuple(_parse_chunk(item, chunks_path) for item in chunks_raw)

    if len(chunks) != manifest.chunk_count:
        raise ValueError(
            f"invalid {chunks_path}: chunk count {len(chunks)} does not match "
            f"manifest chunk_count {manifest.chunk_count}"
        )

    raw_embeddings: NDArray[np.float32] = np.load(embeddings_path, allow_pickle=False)
    if raw_embeddings.dtype != np.float32:
        raise ValueError(f"invalid {embeddings_path}: dtype must be float32")
    expected_shape = (manifest.chunk_count, manifest.dimensions)
    if raw_embeddings.shape != expected_shape:
        raise ValueError(f"invalid {embeddings_path}: shape must be {expected_shape}")
    if not np.all(np.isfinite(raw_embeddings)):
        raise ValueError(f"invalid {embeddings_path}: values must be finite")
    norms: NDArray[np.float32] = np.linalg.norm(raw_embeddings, axis=1)
    if not np.all(np.abs(norms - 1.0) <= _NORM_TOLERANCE):
        raise ValueError(f"invalid {embeddings_path}: every row must be unit-norm")

    return LoadedIndex(manifest=manifest, chunks=chunks, embeddings=raw_embeddings)

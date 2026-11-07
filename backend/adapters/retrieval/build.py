"""Index build CLI (D4): chunks the normalized rulebook, embeds it, writes the index.

Run with `uv run --env-file .env python -m backend.adapters.retrieval.build`. Needs
`OPENROUTER_API_KEY` and `MODEL_EMBEDDINGS`; writes nothing on any failure (every batch
must succeed before `write_index` runs).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from backend.adapters.openrouter import (
    EMBEDDINGS_TIMEOUT_S,
    OpenRouterEmbedder,
    make_openrouter_client,
)
from backend.adapters.retrieval.chunking import (
    EMBED_MAX_CHARS,
    IndexChunk,
    build_chunks,
)
from backend.adapters.retrieval.embedder import Embedder
from backend.adapters.retrieval.index import IndexManifest, write_index
from backend.domain.rulebook import Move, Section, move_from_dict, section_from_dict
from backend.ports.errors import PortError

DEFAULT_NORMALIZED_DIR: Final = Path("data/normalized")
DEFAULT_OUT_DIR: Final = Path("data/index")


def make_embedder(api_key: str, model: str) -> Embedder:
    client = make_openrouter_client(api_key, timeout=EMBEDDINGS_TIMEOUT_S)
    return OpenRouterEmbedder(client, model)


def _load_sections_and_moves(normalized_dir: Path) -> tuple[list[Section], list[Move]]:
    sections_raw = json.loads(
        (normalized_dir / "sections.json").read_text(encoding="utf-8")
    )
    moves_raw = json.loads((normalized_dir / "moves.json").read_text(encoding="utf-8"))
    sections = [section_from_dict(item) for item in sections_raw]
    moves = [move_from_dict(item) for item in moves_raw]
    return sections, moves


def _embed_texts(chunks: Sequence[IndexChunk]) -> list[str]:
    texts: list[str] = []
    for chunk in chunks:
        text = chunk.index_text
        if len(text) > EMBED_MAX_CHARS:
            print(
                f"index-build: warning: truncated {chunk.chunk_id} ({len(text)} chars)",
                file=sys.stderr,
            )
        texts.append(text[:EMBED_MAX_CHARS])
    return texts


def _summary(chunks: Sequence[IndexChunk], manifest: IndexManifest, model: str) -> str:
    move_count = sum(1 for chunk in chunks if chunk.type == "move")
    split_sections = len({chunk.section_id for chunk in chunks if chunk.parts > 1})
    max_chars = max((len(chunk.text) for chunk in chunks), default=0)
    return (
        f"index-build: {manifest.chunk_count} chunks "
        f"({move_count} moves, {split_sections} split sections, "
        f"max {max_chars} chars), {manifest.dimensions} dims, model {model}"
    )


def main(
    argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None
) -> int:
    env = environ if environ is not None else os.environ

    parser = argparse.ArgumentParser(prog="python -m backend.adapters.retrieval.build")
    parser.add_argument("--normalized", type=Path, default=DEFAULT_NORMALIZED_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    api_key = env.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("index-build: error: OPENROUTER_API_KEY is required", file=sys.stderr)
        return 2
    model = env.get("MODEL_EMBEDDINGS", "").strip()
    if not model:
        print("index-build: error: MODEL_EMBEDDINGS is required", file=sys.stderr)
        return 2

    try:
        sections, moves = _load_sections_and_moves(args.normalized)
        chunks = build_chunks(sections, moves)
        embedder = make_embedder(api_key, model)
        texts = _embed_texts(chunks)
        vectors = asyncio.run(embedder.embed(texts))
        manifest = write_index(args.out, chunks, vectors, model)
    except (PortError, ValueError, FileNotFoundError, OSError) as exc:
        print(f"index-build: error: {exc}", file=sys.stderr)
        return 2

    print(_summary(chunks, manifest, model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

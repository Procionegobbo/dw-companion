"""Command-line entry point: `uv run python -m ingestion`.

See the spec's Configuration table for the flags, exit codes and stdout report format.
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from ingestion.manifest import CHAPTERS
from ingestion.pipeline import DEFAULT_MAX_UNKNOWN, IngestionError, build, write


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be an integer >= 0")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingestion")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("vendor/dungeon-world/text"),
        help="Directory containing the manifest's XML files.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/normalized"),
        help="Output directory (created if missing).",
    )
    parser.add_argument(
        "--max-unknown",
        type=_non_negative_int,
        default=DEFAULT_MAX_UNKNOWN,
        help="Build fails if total unknown-markup occurrences exceed this.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = _build_parser().parse_args(argv)

    try:
        result = build(args.source)
    except IngestionError as error:
        print(f"ingestion: error: {error}", file=sys.stderr)
        return 2

    rolled = sum(1 for move in result.moves if move.outcomes is not None)
    print(
        f"ingestion: {len(CHAPTERS)} chapters, {len(result.sections)} sections, "
        f"{len(result.moves)} moves ({rolled} rolled), {len(result.classes)} classes"
    )
    print(f"ingestion: move overrides applied: {result.overrides_applied}")
    print(
        f"ingestion: unknown markup: {result.unknown_total} "
        f"(threshold {args.max_unknown})"
    )
    for key in sorted(result.unknown):
        print(f"  {key}: {result.unknown[key]}")

    if result.unknown_total > args.max_unknown:
        return 1

    write(result, args.out)
    return 0

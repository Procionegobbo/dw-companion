"""Tests for the build pipeline, serialization, and CLI."""

import json
import shutil
from pathlib import Path

import pytest

from ingestion.cli import main
from ingestion.pipeline import BuildResult, build, serialize

from .conftest import REPO_ROOT, SOURCE_DIR

_INJECTION_TARGET = "Are you ready to face them?"
_INJECTED_TAG = "<Sparkle>shiny</Sparkle>"


def test_real_source_has_no_unknown_markup(real_build: BuildResult) -> None:
    assert real_build.unknown == {}


def test_committed_output_matches_fresh_build(real_build: BuildResult) -> None:
    serialized = serialize(real_build)
    for filename, text in serialized.items():
        committed_path = REPO_ROOT / "data" / "normalized" / filename
        committed = committed_path.read_text(encoding="utf-8")
        assert text == committed, (
            "normalized output is stale: run `uv run python -m ingestion` "
            "and review the diff"
        )


def test_serialization_is_deterministic() -> None:
    first = serialize(build(SOURCE_DIR))
    second = serialize(build(SOURCE_DIR))
    assert first == second


def test_cli_writes_three_files_and_reports_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "out"
    exit_code = main(["--source", str(SOURCE_DIR), "--out", str(out_dir)])

    assert exit_code == 0
    assert (out_dir / "sections.json").is_file()
    assert (out_dir / "moves.json").is_file()
    assert (out_dir / "classes.json").is_file()

    captured = capsys.readouterr()
    assert "21 moves (15 rolled), 8 classes" in captured.out
    assert "unknown markup: 0 (threshold 0)" in captured.out


def _inject_unknown_markup(source_copy: Path) -> None:
    intro = source_copy / "Introduction.xml"
    text = intro.read_text(encoding="utf-8")
    patched = text.replace(_INJECTION_TARGET, f"{_INJECTION_TARGET} {_INJECTED_TAG}", 1)
    assert patched != text, "fixture text not found in Introduction.xml"
    intro.write_text(patched, encoding="utf-8")


def test_cli_exits_1_and_writes_nothing_when_unknown_markup_exceeds_threshold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_copy = tmp_path / "source"
    shutil.copytree(SOURCE_DIR, source_copy)
    _inject_unknown_markup(source_copy)

    out_dir = tmp_path / "out"
    exit_code = main(["--source", str(source_copy), "--out", str(out_dir)])

    assert exit_code == 1
    assert list(out_dir.glob("*.json")) == []

    captured = capsys.readouterr()
    assert "tag:Sparkle: 1" in captured.out


def test_cli_raised_threshold_accepts_unknown_markup_and_keeps_text(
    tmp_path: Path,
) -> None:
    source_copy = tmp_path / "source"
    shutil.copytree(SOURCE_DIR, source_copy)
    _inject_unknown_markup(source_copy)

    out_dir = tmp_path / "out"
    exit_code = main(
        ["--source", str(source_copy), "--out", str(out_dir), "--max-unknown", "1"]
    )

    assert exit_code == 0
    sections = json.loads((out_dir / "sections.json").read_text(encoding="utf-8"))
    # The injected tag sits right after "...face them?" in Introduction.xml, which
    # renders into the "Dungeon World" h2 section (introduction/dungeon-world), not
    # the (consumed, empty) chapter section itself.
    section = next(s for s in sections if s["id"] == "introduction/dungeon-world")
    assert f"{_INJECTION_TARGET} shiny" in section["text_markdown"]


def test_cli_exits_2_on_missing_source_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"
    exit_code = main(["--source", str(missing)])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("ingestion: error:")

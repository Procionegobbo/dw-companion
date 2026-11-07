"""Shared fixtures and helpers for ingestion tests.

`SOURCE_DIR` points at the real, vendored source. `real_build` builds it once per test
session (most tests on the real source are read-only assertions over the same result).
`make_source` writes a tiny synthetic source for unit tests that need full control over
chapter ids, titles and markup.
"""

from pathlib import Path

import pytest

from ingestion.manifest import Chapter
from ingestion.pipeline import BuildResult, build

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = REPO_ROOT / "vendor" / "dungeon-world" / "text"

_AID_XMLNS = 'xmlns:aid="http://ns.adobe.com/AdobeInDesign/4.0/"'


@pytest.fixture(scope="session")
def real_build() -> BuildResult:
    if not SOURCE_DIR.is_dir():
        pytest.fail(
            f"{SOURCE_DIR} is missing - run 'git submodule update --init' "
            "to check out the vendored source."
        )
    return build(SOURCE_DIR)


def make_source(
    tmp_path: Path, files: dict[str, str]
) -> tuple[Path, tuple[Chapter, ...]]:
    """Write one synthetic chapter file per entry and return a matching manifest.

    Each key in `files` is a chapter id; its value is the XML to put inside that
    chapter's `<Root>` (e.g. `"<h1>Notes</h1><p>Text.</p>"`), written to
    `<id>.xml` under a fresh source directory. The chapter title is derived from the
    id the same way the real manifest derives titles from file names: kebab-case ->
    Title Case (e.g. "character-creation" -> "Character Creation").
    """
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    chapters: list[Chapter] = []
    for chapter_id, body in files.items():
        (source_dir / f"{chapter_id}.xml").write_text(
            f"<Root {_AID_XMLNS}>{body}</Root>", encoding="utf-8"
        )
        title = chapter_id.replace("-", " ").title()
        chapters.append(Chapter(f"{chapter_id}.xml", chapter_id, title))
    return source_dir, tuple(chapters)

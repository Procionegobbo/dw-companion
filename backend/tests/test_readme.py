"""Guards README.md and docs/development.md structure, links, ADRs and placeholders.

These checks keep the handoff-11 README from drifting: wrong section order, a broken
relative link, a citation to an ADR that does not exist, a leaked `{{...}}` template
token or an unmanaged `TODO`, and an unclosed/nested HTML comment that could hide
content. They never fail because an owner slot (`TODO-OWNER(<id>)`) is still unfilled
(spec 012 D11) - the tests are offline, read files only, and make no network call.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

OWNER_SLOTS = frozenset(
    {"demo-url", "demo-gif", "eval-results", "eval-comparison", "cost-latency"}
)

REQUIRED_HEADINGS = [
    "The problem",
    "Live demo",
    "What the assistant does (and what it doesn't do with AI)",
    "Architecture",
    "Evaluation",
    "Cost, latency and guardrails",
    "Trade-offs and decisions",
    "What I'd do next",
    "Attribution",
]

ATTRIBUTION_STRINGS = [
    "Sage LaTorra",
    "Adam Koebel",
    "https://github.com/Sagelt/Dungeon-World",
    "CC BY 3.0",
    "adapted",
    "unofficial",
    "MIT",
    "ATTRIBUTION.md",
    "LICENSE",
]

DEVELOPMENT_GUIDE_STRINGS = [
    "## Running the assistant locally",
    "## Running the API and chat widget locally",
    "## Running evals",
    "## Running the container and deploying",
    "uv run pytest",
]

_FENCE_PATTERN = re.compile(r"```.*?```", re.DOTALL)
_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING_PATTERN = re.compile(r"^## (.+)$", re.MULTILINE)
_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_ADR_PATTERN = re.compile(r"ADR-\d{3}")
_ADR_HEADING_PATTERN = re.compile(r"^## (ADR-\d{3}):", re.MULTILINE)
_BAD_TODO_PATTERN = re.compile(r"TODO(?!-OWNER\()")
_OWNER_TOKEN_PATTERN = re.compile(r"TODO-OWNER\(([^)]*)\)")


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _strip_code_and_comments(text: str) -> str:
    """Remove fenced code blocks and HTML comments so checks ignore their contents."""
    without_fences = _FENCE_PATTERN.sub("", text)
    return _COMMENT_PATTERN.sub("", without_fences)


def _section(text: str, heading: str) -> str:
    """Return the text between `## {heading}` and the next `## ` line (exclusive)."""
    lines = text.splitlines()
    marker = f"## {heading}"
    start = None
    for index, line in enumerate(lines):
        if line == marker:
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _heading_order_problems(text: str, required: list[str]) -> list[str]:
    stripped = _strip_code_and_comments(text)
    headings = _HEADING_PATTERN.findall(stripped)
    if headings != required:
        return [
            f"heading order mismatch: expected {required!r}, found {headings!r}",
        ]
    return []


def _broken_links(text: str, base_dir: Path) -> list[str]:
    stripped = _strip_code_and_comments(text)
    problems: list[str] = []
    for target in _LINK_PATTERN.findall(stripped):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        file_part = target.split("#", 1)[0]
        if not file_part:
            continue
        if not (base_dir / file_part).exists():
            problems.append(file_part)
    return problems


def _unknown_adr_references(readme_text: str, decisions_text: str) -> list[str]:
    stripped = _strip_code_and_comments(readme_text)
    known = set(_ADR_HEADING_PATTERN.findall(decisions_text))
    referenced = set(_ADR_PATTERN.findall(stripped))
    return sorted(referenced - known)


def _placeholder_problems(text: str) -> list[str]:
    problems: list[str] = []
    if "{{" in text:
        problems.append("contains '{{'")
    if "}}" in text:
        problems.append("contains '}}'")
    if "TBD" in text:
        problems.append("contains 'TBD'")
    for match in _BAD_TODO_PATTERN.finditer(text):
        problems.append(f"bare TODO at position {match.start()}")
    for slot_id in _OWNER_TOKEN_PATTERN.findall(text):
        if slot_id not in OWNER_SLOTS:
            problems.append(f"unknown owner slot id: {slot_id!r}")
    return problems


def _unbalanced_comments(text: str) -> list[str]:
    problems: list[str] = []
    depth = 0
    pos = 0
    while True:
        open_index = text.find("<!--", pos)
        close_index = text.find("-->", pos)
        if open_index == -1 and close_index == -1:
            break
        if open_index != -1 and (close_index == -1 or open_index < close_index):
            if depth > 0:
                problems.append(f"nested '<!--' at position {open_index}")
            depth += 1
            pos = open_index + len("<!--")
        else:
            if depth == 0:
                problems.append(f"unmatched '-->' at position {close_index}")
            else:
                depth -= 1
            pos = close_index + len("-->")
    if depth > 0:
        problems.append("unclosed '<!--'")
    return problems


# --- Repository tests (spec 012-002 Testing) ---------------------------------------


def test_readme_sections_in_required_order() -> None:
    readme = _read("README.md")
    assert _heading_order_problems(readme, REQUIRED_HEADINGS) == []


def test_readme_attribution_states_licensing_split() -> None:
    readme = _read("README.md")
    section = _section(readme, "Attribution")
    for required in ATTRIBUTION_STRINGS:
        assert required in section, f"missing {required!r} in ## Attribution"


def test_readme_relative_links_resolve() -> None:
    readme = _read("README.md")
    broken = _broken_links(readme, REPO_ROOT)
    assert broken == [], f"broken links in README.md: {broken}"


def test_development_doc_links_resolve() -> None:
    development = _read("docs/development.md")
    broken = _broken_links(development, REPO_ROOT / "docs")
    assert broken == [], f"broken links in docs/development.md: {broken}"


def test_readme_adr_references_exist() -> None:
    readme = _read("README.md")
    decisions = _read("docs/decisions.md")
    unknown = _unknown_adr_references(readme, decisions)
    assert unknown == [], f"unknown ADR references in README.md: {unknown}"
    assert _ADR_PATTERN.search(_strip_code_and_comments(readme)) is not None, (
        "README.md must reference at least one ADR"
    )


def test_readme_has_no_unmanaged_placeholders() -> None:
    readme = _read("README.md")
    assert _placeholder_problems(readme) == []


def test_readme_html_comments_are_well_formed() -> None:
    readme = _read("README.md")
    assert _unbalanced_comments(readme) == []


def test_readme_reproduction_commands_match_makefile() -> None:
    readme = _read("README.md")
    assert "make eval" in readme
    assert "make compare" in readme
    makefile = _read("Makefile")
    assert re.search(r"^eval:", makefile, re.MULTILINE) is not None
    assert re.search(r"^compare:", makefile, re.MULTILINE) is not None


def test_development_doc_has_moved_sections() -> None:
    development = _read("docs/development.md")
    assert development.startswith("# Development")
    for required in DEVELOPMENT_GUIDE_STRINGS:
        assert required in development, f"missing {required!r} in docs/development.md"


# --- Negative tests for the check helpers (spec 012-002 Testing) -------------------


def test_heading_check_rejects_wrong_order() -> None:
    text = "## Live demo\n\ntext\n\n## The problem\n\ntext\n"
    problems = _heading_order_problems(text, ["The problem", "Live demo"])
    assert problems != []


def test_link_check_reports_missing_file(tmp_path: Path) -> None:
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "README.md").write_text("content", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text(
        "\n".join(
            [
                "[missing](missing.md)",
                "[external](https://example.com)",
                "[anchor](#anchor)",
                "[fragment](evals/README.md#tuning-round)",
                "```",
                "[fenced](also-missing.md)",
                "```",
                "<!-- [commented](also-missing.md) -->",
            ]
        ),
        encoding="utf-8",
    )
    broken = _broken_links(doc.read_text(encoding="utf-8"), tmp_path)
    assert broken == ["missing.md"]


def test_adr_check_reports_unknown_number() -> None:
    decisions = "## ADR-001: Something\n"
    readme = "See [ADR-999](docs/decisions.md)."
    unknown = _unknown_adr_references(readme, decisions)
    assert unknown == ["ADR-999"]


def test_placeholder_check_rejects_bad_tokens() -> None:
    text = "TODO-OWNER(demo_gif) TODO TBD {{adr:graph}} TODO-OWNER(demo-url)"
    problems = _placeholder_problems(text)
    assert any("demo_gif" in problem for problem in problems)
    assert any("bare TODO" in problem for problem in problems)
    assert any("TBD" in problem for problem in problems)
    assert any("{{" in problem for problem in problems)
    assert not any("demo-url" in problem for problem in problems)


def test_comment_check_rejects_nested_comment() -> None:
    text = "<!-- a <!-- b --> c -->"
    assert _unbalanced_comments(text) != []
    markers = "<!-- comparison-table:start -->\ncontent\n<!-- comparison-table:end -->"
    assert _unbalanced_comments(markers) == []

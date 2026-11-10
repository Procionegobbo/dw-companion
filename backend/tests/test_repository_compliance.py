"""Repository-level compliance tests: licensing, attribution, submodule and env example.

These guard the CC BY 3.0 / SRD 5.1 obligations and the MIT licence split described in
ATTRIBUTION.md, so a regression in those files is caught by `uv run pytest` rather than
by manual review.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

UPSTREAM_URL = "https://github.com/Sagelt/Dungeon-World"
CC_BY_3_URL = "https://creativecommons.org/licenses/by/3.0/"
CC_BY_4_LEGALCODE_URL = "https://creativecommons.org/licenses/by/4.0/legalcode"
PINNED_COMMIT = "e67bd51c09d24518a7f989149b76094fbcc7fecc"

ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*=$")

SECRET_WORKFLOWS = frozenset({"evals.yml"})


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_attribution_credits_authors_source_and_license() -> None:
    attribution = _read("ATTRIBUTION.md")
    assert "Sage LaTorra" in attribution
    assert "Adam Koebel" in attribution
    assert UPSTREAM_URL in attribution
    assert CC_BY_3_URL in attribution


def test_attribution_states_adaptation_and_unofficial_status() -> None:
    attribution = _read("ATTRIBUTION.md")
    assert "adapted" in attribution
    assert "unofficial" in attribution


def test_attribution_reproduces_srd_notice() -> None:
    attribution = _read("ATTRIBUTION.md")
    assert "SRD 5.1" in attribution
    assert CC_BY_4_LEGALCODE_URL in attribution


def test_attribution_records_pinned_commit() -> None:
    attribution = _read("ATTRIBUTION.md")
    assert PINNED_COMMIT in attribution


def test_license_is_mit() -> None:
    license_text = _read("LICENSE")
    first_line = license_text.splitlines()[0]
    assert first_line == "MIT License"


def test_readme_has_attribution_section() -> None:
    readme = _read("README.md")
    lines = readme.splitlines()
    assert "## Attribution" in lines

    start = lines.index("## Attribution") + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    section = "\n".join(lines[start:end])

    assert "ATTRIBUTION.md" in section
    assert "unofficial" in section


def test_vendored_source_is_checked_out() -> None:
    license_path = REPO_ROOT / "vendor" / "dungeon-world" / "LICENSE"
    assert license_path.exists(), (
        "vendor/dungeon-world/LICENSE is missing - run "
        "'git submodule update --init' to check out the vendored source."
    )
    license_text = license_path.read_text(encoding="utf-8")
    assert "Creative Commons Attribution 3.0" in license_text


def test_env_example_declares_keys_without_values() -> None:
    lines = _read(".env.example").splitlines()
    keys: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        error = f"invalid .env.example line: {stripped!r}"
        assert ENV_KEY_PATTERN.match(stripped), error
        keys.append(stripped.split("=", 1)[0])

    expected_keys = [
        "MODEL_ROUTER",
        "MODEL_CLASSIFIER",
        "MODEL_ANSWER",
        "MODEL_EMBEDDINGS",
        "OPENROUTER_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
        "CHAT_RATE_PER_MINUTE",
        "CHAT_RATE_PER_DAY",
        "CHAT_DAILY_BUDGET_USD",
        "CHAT_TRUSTED_PROXY_HOPS",
        "SITE_DIR",
    ]
    assert keys == expected_keys
    assert len(keys) == len(set(keys))


def test_ci_workflows_reference_no_secrets() -> None:
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    yaml_files = sorted(workflows_dir.glob("*.yml")) if workflows_dir.is_dir() else []
    assert yaml_files, (
        ".github/workflows must exist and contain at least one *.yml file - "
        "run the CI workflow story before this test."
    )

    for path in yaml_files:
        if path.name in SECRET_WORKFLOWS:
            continue
        assert "secrets." not in path.read_text(encoding="utf-8"), (
            f"{path.relative_to(REPO_ROOT)} must not reference secrets."
        )


def test_secret_workflows_are_manual_only() -> None:
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    for name in SECRET_WORKFLOWS:
        path = workflows_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert "workflow_dispatch" in text, f"{name} must trigger on workflow_dispatch"
        for forbidden in ("pull_request", "push:", "schedule:"):
            assert forbidden not in text, f"{name} must not contain {forbidden!r}"

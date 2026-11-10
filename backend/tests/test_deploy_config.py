"""Static checks on the committed container-image configuration (spec 011 Testing).

These guard `Dockerfile` and `.dockerignore` without building an image, so a
regression in the deploy configuration is caught by `uv run pytest` rather than by
`make image` alone. The CI `image` job (spec 011 CI Image Job) is the image-level
test that actually builds and smoke-tests the container.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_ARG_PATTERN = re.compile(r"^ARG (\w+)=(\S+)$")
_RUNTIME_ENV_LINE_PATTERN = re.compile(r'^([A-Z][A-Z0-9_]*): "([^"\\]*)"$')
_FORBIDDEN_RUNTIME_ENV_KEYS = frozenset(
    {"OPENROUTER_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "SITE_DIR"}
)


def _dockerfile_text() -> str:
    return (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")


def _env_example_keys() -> set[str]:
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    return {
        line.split("=", 1)[0]
        for line in lines
        if line.strip() and not line.startswith("#") and "=" in line
    }


def _stages(text: str) -> list[str]:
    """Splits the Dockerfile into stages, each starting at a `FROM` line."""
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("FROM ")]
    ends = [*starts[1:], len(lines)]
    return [
        "\n".join(lines[start:end]) for start, end in zip(starts, ends, strict=True)
    ]


def test_dockerignore_is_allow_list() -> None:
    lines = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    non_comment = [line for line in lines if line and not line.startswith("#")]

    assert non_comment[0] == "*"

    bang_lines = {line for line in non_comment if line.startswith("!")}
    assert bang_lines == {
        "!pyproject.toml",
        "!uv.lock",
        "!.python-version",
        "!backend/",
        "!data/normalized/",
        "!data/index/",
        "!site/",
    }
    assert "backend/tests/" in non_comment
    assert "site/node_modules/" in non_comment


def test_dockerfile_never_copies_secrets_or_vendor() -> None:
    lines = _dockerfile_text().splitlines()

    copy_lines = [line for line in lines if line.startswith(("COPY ", "ADD "))]
    assert copy_lines, "Dockerfile must contain at least one COPY/ADD line"
    for line in copy_lines:
        assert "vendor" not in line
        assert ".env" not in line
        assert ".git" not in line

    declare_lines = [line for line in lines if line.startswith(("ARG ", "ENV "))]
    assert declare_lines, "Dockerfile must declare at least one ARG/ENV"
    for line in declare_lines:
        assert "OPENROUTER_API_KEY" not in line
        assert "LANGFUSE_" not in line


def test_runtime_stage_runs_as_non_root() -> None:
    last_stage_lines = _stages(_dockerfile_text())[-1].splitlines()

    copy_indices = [
        index for index, line in enumerate(last_stage_lines) if line.startswith("COPY")
    ]
    user_indices = [
        index
        for index, line in enumerate(last_stage_lines)
        if line.strip() == "USER app"
    ]

    assert copy_indices, "the runtime stage must contain a COPY"
    assert user_indices, "the runtime stage must contain USER app"
    assert user_indices[0] > copy_indices[-1]


def test_runtime_command_matches_api_constraints() -> None:
    cmd_lines = [
        line for line in _dockerfile_text().splitlines() if line.startswith("CMD ")
    ]
    assert len(cmd_lines) == 1
    cmd_line = cmd_lines[0]

    for fragment in (
        "backend.api.app:create_app",
        "--factory",
        "--workers 1",
        "--no-access-log",
        "--proxy-headers",
        "${PORT:-8080}",
    ):
        assert fragment in cmd_line


def test_runtime_stage_sets_site_dir() -> None:
    last_stage_lines = _stages(_dockerfile_text())[-1].splitlines()

    env_lines = [line for line in last_stage_lines if line.startswith("ENV ")]
    assert any("SITE_DIR=/app/site/dist" in line for line in env_lines)
    assert any(
        line.startswith("COPY --from=site /src/site/dist/") for line in last_stage_lines
    )


def test_image_versions_match_toolchain() -> None:
    args: dict[str, str] = {}
    for line in _dockerfile_text().splitlines():
        match = _ARG_PATTERN.match(line)
        if match:
            args[match.group(1)] = match.group(2)

    python_version = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    python_tag = args["PYTHON_IMAGE"].split(":", 1)[1]
    assert python_tag.startswith(f"{python_version}-")

    node_major = (REPO_ROOT / "site" / ".nvmrc").read_text(encoding="utf-8").strip()
    node_tag = args["NODE_IMAGE"].split(":", 1)[1]
    assert node_tag.split("-", 1)[0] == node_major

    assert re.match(r"^\d+\.\d+\.\d+$", args["UV_VERSION"])


def test_infra_scripts_are_strict_and_executable() -> None:
    for name in ("setup.sh", "deploy.sh", "smoke.sh"):
        path = REPO_ROOT / "infra" / name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in text
        assert os.access(path, os.X_OK), f"{name} must be executable"


def test_deploy_pins_single_instance_and_secrets() -> None:
    text = (REPO_ROOT / "infra" / "deploy.sh").read_text(encoding="utf-8")

    for fragment in (
        "--max-instances=1",
        '--min-instances="$MIN_INSTANCES"',
        "--allow-unauthenticated",
        "--env-vars-file=infra/runtime-env.yaml",
        "OPENROUTER_API_KEY=dw-companion-openrouter-api-key:latest",
        "LANGFUSE_PUBLIC_KEY=dw-companion-langfuse-public-key:latest",
        "LANGFUSE_SECRET_KEY=dw-companion-langfuse-secret-key:latest",
    ):
        assert fragment in text, f"deploy.sh is missing {fragment!r}"

    assert re.search(r'MIN_INSTANCES="\$\{MIN_INSTANCES:-\}"', text) or re.search(
        r'MIN_INSTANCES="1"', text
    ), "deploy.sh must default MIN_INSTANCES to 1"


def test_runtime_env_file_is_valid() -> None:
    lines = (
        (REPO_ROOT / "infra" / "runtime-env.yaml")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    non_comment = [
        line for line in lines if line.strip() and not line.strip().startswith("#")
    ]

    env_example_keys = _env_example_keys()

    values: dict[str, str] = {}
    for line in non_comment:
        match = _RUNTIME_ENV_LINE_PATTERN.match(line)
        assert match, f"invalid infra/runtime-env.yaml line: {line!r}"
        key, value = match.group(1), match.group(2)
        assert key not in values, f"duplicate key {key!r} in infra/runtime-env.yaml"
        values[key] = value
        assert key in env_example_keys, f"{key!r} is not declared in .env.example"
        assert key not in _FORBIDDEN_RUNTIME_ENV_KEYS, (
            f"{key!r} must not be committed to infra/runtime-env.yaml"
        )

    assert values["CHAT_TRUSTED_PROXY_HOPS"] == "1"

    manifest_path = REPO_ROOT / "data" / "index" / "manifest.json"
    if not manifest_path.exists():
        pytest.skip("data/index/manifest.json not committed (spec 007 open risk f)")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert values["MODEL_EMBEDDINGS"] == manifest["embedding_model"]


def test_secret_env_vars_documented() -> None:
    env_example_keys = _env_example_keys()
    for key in ("OPENROUTER_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        assert key in env_example_keys


def test_cleanup_policy_keeps_recent_versions() -> None:
    policy = json.loads(
        (REPO_ROOT / "infra" / "ar-cleanup-policy.json").read_text(encoding="utf-8")
    )

    keep_policies = [p for p in policy if p["action"]["type"] == "Keep"]
    delete_policies = [p for p in policy if p["action"]["type"] == "Delete"]

    assert len(keep_policies) == 1
    assert keep_policies[0]["mostRecentVersions"]["keepCount"] == 3
    assert len(delete_policies) == 1

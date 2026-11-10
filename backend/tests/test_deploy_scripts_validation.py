"""Behavioural tests for `infra/setup.sh` and `infra/deploy.sh` input validation
(spec 011 Validation Rules; story's "Script input validation" scenario outline).

These actually execute the scripts as subprocesses - unlike `test_deploy_config.py`,
which only inspects their text - but only to exercise the fail-fast validation
branches that every script runs before it ever touches `gcloud` or `docker`. Each
test therefore shadows `gcloud` and `docker` on `PATH` with fake executables that
log any invocation and exit non-zero, then asserts the log stays empty: a failing
assertion would mean a validation bug let the script reach a real cloud or build
call. No real `gcloud`/`docker` call is ever made. The happy path (an actual
build/push/deploy) needs real GCP credentials and stays out of scope here.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALID_PROJECT = "valid-project-id"
_TIMEOUT_S = 15


def _copy_script(sandbox: Path, name: str) -> Path:
    """Copies `infra/<name>` into an isolated `sandbox/infra/<name>`, so the
    script's own `cd "$(dirname "$0")/.."` lands in a throwaway directory rather
    than the real repo (whose working tree is not under this test's control)."""
    infra_dir = sandbox / "infra"
    infra_dir.mkdir(parents=True, exist_ok=True)
    source = (REPO_ROOT / "infra" / name).read_text(encoding="utf-8")
    destination = infra_dir / name
    destination.write_text(source, encoding="utf-8")
    destination.chmod(0o755)
    return destination


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _git_init_with_commit(sandbox: Path) -> None:
    """Commits everything already written under `sandbox`, giving it a clean
    working tree and a HEAD commit (`git rev-parse HEAD` needs one)."""
    _git("init", "-q", cwd=sandbox)
    _git("config", "user.email", "test@example.invalid", cwd=sandbox)
    _git("config", "user.name", "Test", cwd=sandbox)
    _git("add", "-A", cwd=sandbox)
    _git("commit", "-q", "-m", "sandbox init", cwd=sandbox)


def _fake_bin_dir(tmp_path: Path, call_log: Path) -> Path:
    """Creates a directory with fake `gcloud` and `docker` executables that
    append their invocation to `call_log` and exit 99. Prepending this directory
    to `PATH` lets a script's own `command -v gcloud`/`command -v docker` checks
    succeed (the executables exist) while guaranteeing neither is ever actually
    run for real against a cloud project."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    log = shlex.quote(str(call_log))
    for name in ("gcloud", "docker"):
        stub = bin_dir / name
        stub.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s %s\\n' {shlex.quote(name)} \"$*\" >> {log}\n"
            "exit 99\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
    return bin_dir


def _env(bin_dir: Path, **overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    for key in ("GCP_PROJECT", "GCP_REGION", "MIN_INSTANCES"):
        env.pop(key, None)
    env.update(overrides)
    return env


def _run(
    script: Path, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
    )


def test_setup_rejects_bad_gcp_project(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    script = _copy_script(sandbox, "setup.sh")
    call_log = tmp_path / "calls.log"
    bin_dir = _fake_bin_dir(tmp_path, call_log)

    for bad_project in ("", "ab", "Invalid-Project", "has_underscore1"):
        result = _run(script, sandbox, _env(bin_dir, GCP_PROJECT=bad_project))
        assert result.returncode == 1, (bad_project, result.stdout, result.stderr)
        assert "setup: error:" in result.stderr
        assert "GCP_PROJECT" in result.stderr

    assert not call_log.exists(), call_log.read_text() if call_log.exists() else ""


def test_setup_rejects_bad_gcp_region(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    script = _copy_script(sandbox, "setup.sh")
    call_log = tmp_path / "calls.log"
    bin_dir = _fake_bin_dir(tmp_path, call_log)

    for bad_region in ("EUROPE-WEST1", "europe_west1", "europe-west", "1-2"):
        result = _run(
            script,
            sandbox,
            _env(bin_dir, GCP_PROJECT=_VALID_PROJECT, GCP_REGION=bad_region),
        )
        assert result.returncode == 1, (bad_region, result.stdout, result.stderr)
        assert "setup: error:" in result.stderr
        assert "GCP_REGION" in result.stderr

    assert not call_log.exists()


def test_deploy_rejects_bad_gcp_project(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    script = _copy_script(sandbox, "deploy.sh")
    call_log = tmp_path / "calls.log"
    bin_dir = _fake_bin_dir(tmp_path, call_log)

    for bad_project in ("", "ab", "Invalid-Project", "has_underscore1"):
        result = _run(script, sandbox, _env(bin_dir, GCP_PROJECT=bad_project))
        assert result.returncode == 1, (bad_project, result.stdout, result.stderr)
        assert "deploy: error:" in result.stderr
        assert "GCP_PROJECT" in result.stderr

    assert not call_log.exists()


def test_deploy_rejects_bad_gcp_region(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    script = _copy_script(sandbox, "deploy.sh")
    call_log = tmp_path / "calls.log"
    bin_dir = _fake_bin_dir(tmp_path, call_log)

    for bad_region in ("EUROPE-WEST1", "europe_west1", "europe-west", "1-2"):
        result = _run(
            script,
            sandbox,
            _env(bin_dir, GCP_PROJECT=_VALID_PROJECT, GCP_REGION=bad_region),
        )
        assert result.returncode == 1, (bad_region, result.stdout, result.stderr)
        assert "deploy: error:" in result.stderr
        assert "GCP_REGION" in result.stderr

    assert not call_log.exists()


def test_deploy_rejects_bad_min_instances(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    script = _copy_script(sandbox, "deploy.sh")
    call_log = tmp_path / "calls.log"
    bin_dir = _fake_bin_dir(tmp_path, call_log)

    for bad_value in ("2", "-1", "yes", "01", "true"):
        result = _run(
            script,
            sandbox,
            _env(bin_dir, GCP_PROJECT=_VALID_PROJECT, MIN_INSTANCES=bad_value),
        )
        assert result.returncode == 1, (bad_value, result.stdout, result.stderr)
        assert "deploy: error:" in result.stderr
        assert "MIN_INSTANCES" in result.stderr

    assert not call_log.exists()


def test_deploy_rejects_dirty_working_tree(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    script = _copy_script(sandbox, "deploy.sh")
    index_dir = sandbox / "data" / "index"
    index_dir.mkdir(parents=True)
    (index_dir / "manifest.json").write_text("{}", encoding="utf-8")
    _git_init_with_commit(sandbox)

    # Dirty the tree *after* the commit, with an untracked file - this alone
    # makes `git status --porcelain` non-empty regardless of the ambient state
    # of the real dw-companion repo this test itself runs from.
    (sandbox / "untracked.txt").write_text("dirty", encoding="utf-8")

    call_log = tmp_path / "calls.log"
    bin_dir = _fake_bin_dir(tmp_path, call_log)
    result = _run(script, sandbox, _env(bin_dir, GCP_PROJECT=_VALID_PROJECT))

    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "deploy: error:" in result.stderr
    assert "working tree is not clean" in result.stderr
    assert not call_log.exists()


def test_deploy_rejects_missing_index(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    script = _copy_script(sandbox, "deploy.sh")
    # No data/index/manifest.json anywhere under the sandbox.
    _git_init_with_commit(sandbox)

    call_log = tmp_path / "calls.log"
    bin_dir = _fake_bin_dir(tmp_path, call_log)
    result = _run(script, sandbox, _env(bin_dir, GCP_PROJECT=_VALID_PROJECT))

    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "deploy: error:" in result.stderr
    assert "data/index/manifest.json" in result.stderr
    assert not call_log.exists()

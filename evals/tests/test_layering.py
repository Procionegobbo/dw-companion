"""Layering guard for `evals/` (spec 009 D8/D16, Testing -> `test_layering.py`):
no file under `evals/` (tests included) may import a vendor SDK directly. Every
seam `evals/` needs from a vendor SDK (an HTTP client type, a span exporter
type) comes from `backend.composition`'s re-exported type aliases instead
(`HttpClientSeam`, `SpanExporterSeam`), so this module stays free of `openai`,
`langfuse`, `httpx2`, `numpy` and `opentelemetry`, following `backend/tests/
test_adapters_layering.py`'s AST-scan pattern.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO_ROOT / "evals"

_VENDOR_SDKS = frozenset({"openai", "langfuse", "httpx2", "numpy", "opentelemetry"})


def _imported_modules(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def test_evals_import_no_vendor_sdks() -> None:
    evals_files = sorted(EVALS_DIR.rglob("*.py"))
    relative_names = {str(path.relative_to(EVALS_DIR)) for path in evals_files}
    assert "run.py" in relative_names, "evals/run.py must be among the scanned files"
    assert "tests/test_cli.py" in relative_names, (
        "evals/tests/test_cli.py must be among the scanned files"
    )

    for path in evals_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree):
            top_level = module.split(".", 1)[0]
            # Imports from `backend.tests.adapter_helpers` (and other
            # `backend.tests.*` helpers) are allowed: they name a local module,
            # never one of the vendor SDKs themselves, so they never match here.
            assert top_level not in _VENDOR_SDKS, (
                f"{path.relative_to(REPO_ROOT)} imports vendor SDK module "
                f"{module!r}; evals/ may never import {sorted(_VENDOR_SDKS)} "
                "directly (spec 009 D8)"
            )

"""Layering guards for `backend/adapters/` (spec 007 D13 style, Architecture / Design
Overview's layering paragraph): adapters never import the graph or the API layer, and
the three new vendor SDKs (plus `httpx2`/`opentelemetry`, spec 007 D21's test seams)
stay confined to adapters, the composition root and tests.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
ADAPTERS_DIR = BACKEND_DIR / "adapters"

_VENDOR_SDKS = frozenset({"openai", "langfuse", "numpy", "httpx2", "opentelemetry"})


def _imported_modules(tree: ast.Module, *, own_package: str) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # Relative import: resolve to the file's own package, regardless of
                # how many levels it climbs.
                modules.append(own_package)
            elif node.module is not None:
                modules.append(node.module)
    return modules


def test_adapters_do_not_import_graph_or_api() -> None:
    adapter_files = sorted(ADAPTERS_DIR.rglob("*.py"))
    relative_names = {str(path.relative_to(ADAPTERS_DIR)) for path in adapter_files}
    assert "openrouter.py" in relative_names, (
        "openrouter.py must be among the scanned adapter files"
    )
    assert "retrieval/hybrid.py" in relative_names, (
        "retrieval/hybrid.py must be among the scanned adapter files"
    )

    for path in adapter_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree, own_package="backend.adapters"):
            forbidden = module in ("backend.graph", "backend.api") or module.startswith(
                ("backend.graph.", "backend.api.")
            )
            assert not forbidden, (
                f"{path.relative_to(REPO_ROOT)} imports {module!r}; "
                "backend/adapters/ must never import backend.graph or backend.api"
            )


def _is_vendor_sdk_location(path: Path) -> bool:
    relative = path.relative_to(BACKEND_DIR)
    parts = relative.parts
    if parts[0] == "adapters":
        return True
    if parts[0] == "tests":
        return True
    return relative == Path("composition.py")


def test_vendor_sdks_confined_to_adapters() -> None:
    backend_files = sorted(BACKEND_DIR.rglob("*.py"))
    assert backend_files, "backend/ must contain scannable files"

    for path in backend_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        own_package = ".".join(("backend", *path.relative_to(BACKEND_DIR).parent.parts))
        for module in _imported_modules(tree, own_package=own_package):
            top_level = module.split(".", 1)[0]
            if top_level not in _VENDOR_SDKS:
                continue
            assert _is_vendor_sdk_location(path), (
                f"{path.relative_to(REPO_ROOT)} imports vendor SDK module {module!r}; "
                f"{sorted(_VENDOR_SDKS)} may only be imported under backend/adapters/, "
                "backend/composition.py or backend/tests/"
            )

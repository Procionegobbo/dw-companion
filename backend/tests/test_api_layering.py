"""Layering guards for `backend/api/` (spec 008 Architecture / Design Overview):
`backend/api/` never imports `backend.adapters` or `langgraph`, and no other
backend package imports `fastapi`, `starlette` or `backend.api`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
API_DIR = BACKEND_DIR / "api"

API_ALLOWED_MODULES = {
    "__future__",
    "asyncio",
    "collections",
    "collections.abc",
    "contextlib",
    "dataclasses",
    "datetime",
    "hashlib",
    "hmac",
    "json",
    "logging",
    "math",
    "os",
    "re",
    "secrets",
    "time",
    "typing",
    "uuid",
}

_API_ALLOWED_GRAPH_MODULES = {
    "backend.graph.builder",
    "backend.graph.state",
    "backend.graph.replies",
}

_WEB_FRAMEWORK_SCAN_DIRS = ("domain", "ports", "graph", "adapters")


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


def _is_api_allowed(module: str) -> bool:
    if module in API_ALLOWED_MODULES:
        return True
    top_level = module.split(".", 1)[0]
    if top_level in {"fastapi", "starlette", "pydantic"}:
        return True
    if module == "backend.api" or module.startswith("backend.api."):
        return True
    if module == "backend.ports" or module.startswith("backend.ports."):
        return True
    if module == "backend.domain" or module.startswith("backend.domain."):
        return True
    if module == "backend.composition":
        return True
    return module in _API_ALLOWED_GRAPH_MODULES


def test_api_imports_allow_list() -> None:
    api_files = sorted(API_DIR.glob("*.py"))
    file_names = {path.name for path in api_files}
    assert "app.py" in file_names, "app.py must be among the scanned api files"

    for path in api_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree, own_package="backend.api"):
            assert _is_api_allowed(module), (
                f"{path.relative_to(REPO_ROOT)} imports disallowed module {module!r}; "
                "backend/api/ may only import "
                f"{sorted(API_ALLOWED_MODULES)}, fastapi/starlette/pydantic, "
                "backend.api.*/backend.ports.*/backend.domain.*, backend.composition "
                f"or {sorted(_API_ALLOWED_GRAPH_MODULES)}"
            )


def _is_web_framework_import(module: str) -> bool:
    top_level = module.split(".", 1)[0]
    if top_level in {"fastapi", "starlette"}:
        return True
    return module == "backend.api" or module.startswith("backend.api.")


def test_web_framework_confined_to_api() -> None:
    paths = [BACKEND_DIR / "composition.py"]
    for sub in _WEB_FRAMEWORK_SCAN_DIRS:
        paths.extend(sorted((BACKEND_DIR / sub).rglob("*.py")))
    assert len(paths) > len(_WEB_FRAMEWORK_SCAN_DIRS), "there must be files to scan"

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(BACKEND_DIR)
        own_package = (
            "backend.composition"
            if relative == Path("composition.py")
            else ".".join(("backend", *relative.parent.parts))
        )
        for module in _imported_modules(tree, own_package=own_package):
            assert not _is_web_framework_import(module), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r}; only backend/api/ "
                "may import fastapi, starlette or backend.api"
            )

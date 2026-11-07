"""Layering guards introduced by spec 006.

Story 1 added the `backend/ports/` import scan and the network guard test; story 2
adds the `backend/graph/` allow-list scan (`test_graph_imports_allow_list`), now that
`backend/graph/` has modules to scan.
"""

from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PORTS_DIR = REPO_ROOT / "backend" / "ports"
GRAPH_DIR = REPO_ROOT / "backend" / "graph"

PORTS_ALLOWED_MODULES = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "math",
    "re",
    "typing",
}

GRAPH_ALLOWED_MODULES = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "json",
    "math",
    "re",
    "time",
    "typing",
}


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


def _is_ports_allowed(module: str) -> bool:
    if module in PORTS_ALLOWED_MODULES:
        return True
    if module == "backend.domain" or module.startswith("backend.domain."):
        return True
    return module == "backend.ports" or module.startswith("backend.ports.")


def _is_graph_allowed(module: str, *, file_name: str) -> bool:
    if module in GRAPH_ALLOWED_MODULES:
        return True
    if module == "backend.domain" or module.startswith("backend.domain."):
        return True
    if module == "backend.ports" or module.startswith("backend.ports."):
        return True
    if module == "backend.graph" or module.startswith("backend.graph."):
        return True
    return file_name == "builder.py" and (
        module == "langgraph" or module.startswith("langgraph.")
    )


def test_ports_import_only_domain_and_stdlib() -> None:
    port_files = sorted(PORTS_DIR.glob("*.py"))
    file_names = {path.name for path in port_files}
    assert "llm.py" in file_names, "llm.py must be among the scanned ports files"

    for path in port_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree, own_package="backend.ports"):
            assert _is_ports_allowed(module), (
                f"{path.relative_to(REPO_ROOT)} imports disallowed module {module!r}; "
                "backend/ports/ may only import "
                f"{sorted(PORTS_ALLOWED_MODULES)} or backend.domain.*/backend.ports.*"
            )


def test_graph_imports_allow_list() -> None:
    graph_files = sorted(GRAPH_DIR.glob("*.py"))
    file_names = {path.name for path in graph_files}
    assert "builder.py" in file_names, (
        "builder.py must be among the scanned graph files"
    )

    for path in graph_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree, own_package="backend.graph"):
            assert _is_graph_allowed(module, file_name=path.name), (
                f"{path.relative_to(REPO_ROOT)} imports disallowed module {module!r}; "
                "backend/graph/ may only import "
                f"{sorted(GRAPH_ALLOWED_MODULES)} or "
                "backend.domain.*/backend.ports.*/backend.graph.* "
                "(builder.py may also import langgraph.*)"
            )


def test_no_network_guard_active() -> None:
    with pytest.raises(RuntimeError, match="network"):
        socket.create_connection(("127.0.0.1", 9))

"""Guards `backend/domain/` purity (D13): no I/O, no framework or LLM imports.

An AST scan of every `backend/domain/*.py` file asserts its imports are limited to the
stdlib allow-list plus other `backend.domain` modules.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_DIR = REPO_ROOT / "backend" / "domain"

ALLOWED_MODULES = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "re",
    "typing",
}


def _imported_modules(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # Relative import: resolve to backend.domain (the only package these
                # files live in), regardless of how many levels it climbs.
                modules.append("backend.domain")
            elif node.module is not None:
                modules.append(node.module)
    return modules


def _is_allowed(module: str) -> bool:
    if module in ALLOWED_MODULES:
        return True
    return module == "backend.domain" or module.startswith("backend.domain.")


def test_domain_imports_are_pure() -> None:
    domain_files = sorted(DOMAIN_DIR.glob("*.py"))
    file_names = {path.name for path in domain_files}
    assert "dice.py" in file_names, "dice.py must be among the scanned domain files"

    for path in domain_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree):
            assert _is_allowed(module), (
                f"{path.relative_to(REPO_ROOT)} imports disallowed module {module!r}; "
                "backend/domain/ may only import "
                f"{sorted(ALLOWED_MODULES)} or other backend.domain submodules"
            )

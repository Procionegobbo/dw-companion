"""Smoke tests for the Python toolchain and the empty hexagonal package layout."""

import importlib
import sys

import pytest


def test_python_runtime_is_at_least_3_12() -> None:
    assert sys.version_info >= (3, 12)


@pytest.mark.parametrize(
    "module_name",
    [
        "backend.domain",
        "backend.ports",
        "backend.adapters",
        "backend.graph",
        "backend.api",
        "ingestion",
    ],
)
def test_layer_package_is_importable(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.__name__ == module_name

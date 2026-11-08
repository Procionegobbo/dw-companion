"""Autouse guard: no evals test may open a network connection (spec 009 D16).

Identical in behaviour to `backend/tests/conftest.py` (spec 006 D24); scoped to
`evals/tests/` by its location, since pytest conftest fixtures apply per directory.
"""

from __future__ import annotations

import socket

import pytest


def _blocked(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("network access is disabled in tests")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

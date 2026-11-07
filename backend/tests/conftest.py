"""Autouse guard: no backend test may open a network connection (D24).

A 10-line monkeypatch rather than a `pytest-socket` dependency (spec 001 Future
Considerations). `asyncio.run` on macOS/Linux uses `socketpair`, not `connect`, so the
event loop used by async graph tests is unaffected (open risk c).
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

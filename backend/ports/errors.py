"""The one exception adapters raise for external failures (D19)."""

from __future__ import annotations


class PortError(Exception):
    """An external dependency behind a port failed (timeout, provider or store error).

    The graph catches only this exception; anything else is a bug and propagates.
    """

"""Pure URL helpers mirroring the spec 004 URL contract (D21).

Stdlib only (`re`): the section id and move slug patterns are spec 002 D5's, repeated
here (rather than imported from `backend.domain.rulebook`) so this module stays a
single, self-contained dependency for spec 007's chunk `anchor_url` and the graph's
move card.
"""

from __future__ import annotations

import re

_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SECTION_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?$")


def section_url(section_id: str) -> str:
    if not _SECTION_ID.fullmatch(section_id):
        raise ValueError(
            f"invalid section_id {section_id!r}: must match {_SECTION_ID.pattern!r}"
        )
    return f"/rules/{section_id}/"


def move_url(move_id: str) -> str:
    if not _SLUG.fullmatch(move_id):
        raise ValueError(f"invalid move_id {move_id!r}: must match {_SLUG.pattern!r}")
    return f"/moves/{move_id}/"

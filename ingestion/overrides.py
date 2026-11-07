"""Hand-maintained move overrides (D11).

Each entry replaces one or more automatically extracted fields of one move with text
that must already appear verbatim in that move's `body_markdown` and must differ from
the automatic result - `ingestion/moves.py` enforces both rules and fails the build
otherwise. See `docs/source-notes.md` section 7 for why each entry exists.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ingestion.models import Stat


@dataclass(frozen=True, slots=True)
class MoveOverride:
    reason: str
    stat: Stat | None = None
    strong_hit: str | None = None
    weak_hit: str | None = None
    miss: str | None = None


MOVE_OVERRIDES: Final[Mapping[str, MoveOverride]] = {
    "defy-danger": MoveOverride(
        reason=(
            "The stat is chosen by approach from a +Str … +Cha list; there is no "
            "roll+STAT phrase."
        ),
        stat="VARIES",
    ),
    "defend": MoveOverride(
        reason="The spend-hold rules and option list that follow apply to both hit bands.",
        weak_hit="On a 7–9, hold 1.",
    ),
    "spout-lore": MoveOverride(
        reason="“The GM might ask you …” applies to both hit bands.",
        weak_hit=(
            "On a 7–9 the GM will only tell you something interesting—it’s on you "
            "to make it useful."
        ),
    ),
    "discern-realities": MoveOverride(
        reason="“Take +1 forward …” and the question list apply to both hit bands.",
        weak_hit="On a 7–9 ask 1.",
    ),
    "carouse": MoveOverride(
        reason="The option list applies to all three bands.",
        miss="On a miss, you still choose one, but things get really out of hand.",
    ),
    "recruit": MoveOverride(
        reason="“If you turn away applicants …” applies regardless of the roll.",
        miss=(
            "On a miss someone influential and ill-suited declares they’d like to "
            "come along (a foolhardy youth, a loose-cannon, or a veiled enemy, for "
            "example), bring them and take the consequences or turn them away."
        ),
    ),
}

"""Shared test helpers for `backend/domain/` tests.

Not collected by pytest (no `test_` prefix). `ScriptedRandom` plus the move/section
fixture dicts used by `test_domain_rulebook.py` (and later `test_domain_outcome.py`).
"""

import pytest


class ScriptedRandom:
    """A `RandomSource` that returns a fixed sequence from `randint`.

    Records every `(a, b)` argument pair it was called with, and fails the test (via
    `pytest.fail`) if more draws are requested than were scripted.
    """

    def __init__(self, values: list[int]) -> None:
        self._values = list(values)
        self.calls: list[tuple[int, int]] = []

    def randint(self, a: int, b: int, /) -> int:
        self.calls.append((a, b))
        if not self._values:
            pytest.fail("ScriptedRandom exhausted: no more scripted values")
        return self._values.pop(0)


# Inline fixtures copied from spec 002's *Expected results for the named moves*.
# `name` is the move's display name, `class` is always None, `section_id` is
# `moves/<id>`, and `body_markdown` is the placeholder "(body)" since the domain only
# checks that it is a `str`.

HACK_AND_SLASH: dict[str, object] = {
    "id": "hack-and-slash",
    "name": "Hack and Slash",
    "category": "basic",
    "class": None,
    "stat": "STR",
    "trigger": "When you attack an enemy in melee",
    "outcomes": {
        "strong_hit": (
            "On a 10+ you deal your damage to the enemy and avoid their attack. At "
            "your option, you may choose to do +1d6 damage but expose yourself to "
            "the enemy\u2019s attack."
        ),
        "weak_hit": (
            "On a 7\u20139, you deal your damage to the enemy and the enemy makes "
            "an attack against you."
        ),
        "miss": None,
    },
    "body_markdown": "(body)",
    "section_id": "moves/hack-and-slash",
}

DEFY_DANGER: dict[str, object] = {
    "id": "defy-danger",
    "name": "Defy Danger",
    "category": "basic",
    "class": None,
    "stat": "VARIES",
    "trigger": "When you act despite an imminent threat or suffer a calamity",
    "outcomes": {
        "strong_hit": (
            "On a 10+, you do what you set out to, the threat doesn\u2019t come "
            "to bear."
        ),
        "weak_hit": (
            "On a 7\u20139, you stumble, hesitate, or flinch: the GM will offer you "
            "a worse outcome, hard bargain, or ugly choice."
        ),
        "miss": None,
    },
    "body_markdown": "(body)",
    "section_id": "moves/defy-danger",
}

VOLLEY: dict[str, object] = {
    "id": "volley",
    "name": "Volley",
    "category": "basic",
    "class": None,
    "stat": "DEX",
    "trigger": "When you take aim and shoot at an enemy at range",
    "outcomes": {
        "strong_hit": "On a 10+ you have a clear shot\u2014deal your damage.",
        "weak_hit": (
            "On a 7\u20139, choose one (whichever you choose you deal your damage):"
            "\n\n"
            "- You have to move to get the shot placing you in danger of the "
            "GM\u2019s choice\n"
            "- You have to take what you can get: -1d6 damage\n"
            "- You have to take several shots, reducing your ammo by one."
        ),
        "miss": None,
    },
    "body_markdown": "(body)",
    "section_id": "moves/volley",
}

DISCERN_REALITIES: dict[str, object] = {
    "id": "discern-realities",
    "name": "Discern Realities",
    "category": "basic",
    "class": None,
    "stat": "WIS",
    "trigger": "When you closely study a situation or person",
    "outcomes": {
        "strong_hit": "On a 10+ ask the GM 3 questions from the list below.",
        "weak_hit": "On a 7\u20139 ask 1.",
        "miss": None,
    },
    "body_markdown": "(body)",
    "section_id": "moves/discern-realities",
}

LAST_BREATH: dict[str, object] = {
    "id": "last-breath",
    "name": "Last Breath",
    "category": "special",
    "class": None,
    "stat": "NONE",
    "trigger": "When you\u2019re dying",
    "outcomes": {
        "strong_hit": (
            "On a 10+ you\u2019ve cheated death\u2014you\u2019re in a bad spot "
            "but you\u2019re still alive."
        ),
        "weak_hit": (
            "On a 7\u20139 Death will offer you a bargain. Take it and stabilize "
            "or refuse and pass beyond the Black Gates into whatever fate awaits "
            "you."
        ),
        "miss": (
            "On a miss, your fate is sealed. You\u2019re marked as Death\u2019s "
            "own and you\u2019ll cross the threshold soon. The GM will tell you "
            "when."
        ),
    },
    "body_markdown": "(body)",
    "section_id": "moves/last-breath",
}

MAKE_CAMP: dict[str, object] = {
    "id": "make-camp",
    "name": "Make Camp",
    "category": "special",
    "class": None,
    "stat": None,
    "trigger": "When you settle in to rest",
    "outcomes": None,
    "body_markdown": "(body)",
    "section_id": "moves/make-camp",
}

NAMED_MOVE_FIXTURES: tuple[dict[str, object], ...] = (
    HACK_AND_SLASH,
    DEFY_DANGER,
    VOLLEY,
    DISCERN_REALITIES,
    LAST_BREATH,
)

CHAPTER_SECTION: dict[str, object] = {
    "id": "moves",
    "chapter": "moves",
    "title": "Moves",
    "slug": "moves",
    "parent_id": None,
    "order": 4,
    "text_markdown": "",
}

CHILD_SECTION: dict[str, object] = {
    "id": "moves/hack-and-slash",
    "chapter": "moves",
    "title": "Hack and Slash",
    "slug": "hack-and-slash",
    "parent_id": "moves",
    "order": 6,
    "text_markdown": "(body)",
}

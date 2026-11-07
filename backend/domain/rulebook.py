"""Immutable, validated rulebook types and parsers for the spec 002 JSON shapes.

Stdlib only (D1): frozen, slotted dataclasses validate their invariants in
`__post_init__`; `Stat`/`AbilityStat`/`Category` are `typing.Literal` vocabularies.
This module re-declares the spec 002 shapes rather than importing `ingestion.models`
(D2) so the runtime backend never needs the offline ingestion package. All failures
raise `ValueError` naming the type and field (D11); invariants are enforced at
construction (D12) so an invalid object cannot exist.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeGuard, cast, get_args

from backend.domain.dice import Band

Stat = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA", "BOND", "VARIES", "NONE"]
AbilityStat = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]
Category = Literal["basic", "special", "class"]

STATS: tuple[Stat, ...] = get_args(Stat)
ABILITY_STATS: tuple[AbilityStat, ...] = get_args(AbilityStat)
_CATEGORIES: tuple[Category, ...] = get_args(Category)

# Spec 002 D5 id patterns.
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SECTION_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?$")

_MOVE_KEYS = frozenset(
    {
        "id",
        "name",
        "category",
        "class",
        "stat",
        "trigger",
        "outcomes",
        "body_markdown",
        "section_id",
    }
)
_OUTCOMES_KEYS = frozenset({"strong_hit", "weak_hit", "miss"})
_SECTION_KEYS = frozenset(
    {"id", "chapter", "title", "slug", "parent_id", "order", "text_markdown"}
)


def is_stat(value: object) -> TypeGuard[Stat]:
    return value in STATS


def is_category(value: object) -> TypeGuard[Category]:
    return value in _CATEGORIES


@dataclass(frozen=True, slots=True)
class Outcomes:
    """A move's three band texts (plural, mirroring the spec 002 JSON key)."""

    strong_hit: str
    weak_hit: str
    miss: str | None

    def __post_init__(self) -> None:
        if not self.strong_hit.strip():
            raise ValueError("invalid outcomes: strong_hit must be non-empty")
        if not self.weak_hit.strip():
            raise ValueError("invalid outcomes: weak_hit must be non-empty")
        if self.miss is not None and not self.miss.strip():
            raise ValueError("invalid outcomes: miss must be non-empty or null")

    def text_for(self, band: Band) -> str | None:
        if band == "strong_hit":
            return self.strong_hit
        if band == "weak_hit":
            return self.weak_hit
        return self.miss


@dataclass(frozen=True, slots=True)
class Move:
    id: str
    name: str
    category: Category
    class_: str | None
    stat: Stat | None
    trigger: str
    outcomes: Outcomes | None
    body_markdown: str
    section_id: str

    def __post_init__(self) -> None:
        ref = self.id
        if not SLUG.fullmatch(self.id):
            raise ValueError(f"invalid move {ref!r}: id must match {SLUG.pattern!r}")
        if not self.name.strip():
            raise ValueError(f"invalid move {ref!r}: name must be non-empty")
        if not self.trigger.strip():
            raise ValueError(f"invalid move {ref!r}: trigger must be non-empty")
        if not is_category(self.category):
            raise ValueError(
                f"invalid move {ref!r}: category must be one of {_CATEGORIES}"
            )
        if self.category == "class":
            if self.class_ is None or not self.class_.strip():
                raise ValueError(
                    f"invalid move {ref!r}: class_ must be non-empty when "
                    "category is 'class'"
                )
        elif self.class_ is not None:
            raise ValueError(
                f"invalid move {ref!r}: class_ must be null unless category is 'class'"
            )
        if (self.stat is None) != (self.outcomes is None):
            raise ValueError(
                f"invalid move {ref!r}: stat and outcomes must both be set or "
                "both be null"
            )
        if self.stat is not None and not is_stat(self.stat):
            raise ValueError(f"invalid move {ref!r}: stat must be one of {STATS}")
        if not SECTION_ID.fullmatch(self.section_id):
            raise ValueError(
                f"invalid move {ref!r}: section_id must match {SECTION_ID.pattern!r}"
            )

    @property
    def is_rolled(self) -> bool:
        return self.outcomes is not None


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    chapter: str
    title: str
    slug: str
    parent_id: str | None
    order: int
    text_markdown: str

    def __post_init__(self) -> None:
        ref = self.id
        if not SECTION_ID.fullmatch(self.id):
            raise ValueError(
                f"invalid section {ref!r}: id must match {SECTION_ID.pattern!r}"
            )
        if not SLUG.fullmatch(self.chapter):
            raise ValueError(
                f"invalid section {ref!r}: chapter must match {SLUG.pattern!r}"
            )
        if not self.title.strip():
            raise ValueError(f"invalid section {ref!r}: title must be non-empty")
        if self.parent_id is None:
            if self.id != self.chapter or self.id != self.slug:
                raise ValueError(
                    f"invalid section {ref!r}: a chapter section's id must equal "
                    "both chapter and slug"
                )
        else:
            if self.id != f"{self.chapter}/{self.slug}":
                raise ValueError(
                    f"invalid section {ref!r}: a child section's id must equal "
                    "'{chapter}/{slug}'"
                )
            if not SECTION_ID.fullmatch(self.parent_id):
                raise ValueError(
                    f"invalid section {ref!r}: parent_id must match "
                    f"{SECTION_ID.pattern!r}"
                )
        if isinstance(self.order, bool):
            raise ValueError(f"invalid section {ref!r}: order must be int, not bool")
        if self.order < 0:
            raise ValueError(f"invalid section {ref!r}: order must be >= 0")


def _key_mismatch_message(
    label: str, ref: str, keys: set[str], expected: frozenset[str]
) -> str | None:
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if not missing and not extra:
        return None
    return f"invalid {label} {ref!r}: missing keys {missing}, unexpected keys {extra}"


def move_from_dict(data: Mapping[str, object]) -> Move:
    if not hasattr(data, "get") or not hasattr(data, "keys"):
        raise ValueError("invalid move '?': expected a mapping")

    raw_id = data.get("id")
    ref = raw_id if isinstance(raw_id, str) else "?"

    mismatch = _key_mismatch_message("move", ref, set(data.keys()), _MOVE_KEYS)
    if mismatch is not None:
        raise ValueError(mismatch)

    id_raw = data["id"]
    if not isinstance(id_raw, str):
        raise ValueError(f"invalid move {ref!r}: id must be str")

    name_raw = data["name"]
    if not isinstance(name_raw, str):
        raise ValueError(f"invalid move {ref!r}: name must be str")

    category_raw = data["category"]
    if not isinstance(category_raw, str):
        raise ValueError(f"invalid move {ref!r}: category must be str")
    if not is_category(category_raw):
        raise ValueError(f"invalid move {ref!r}: category must be one of {_CATEGORIES}")
    category: Category = category_raw

    class_raw = data["class"]
    class_: str | None
    if class_raw is None:
        class_ = None
    elif isinstance(class_raw, str):
        class_ = class_raw
    else:
        raise ValueError(f"invalid move {ref!r}: class must be str or null")

    stat_raw = data["stat"]
    stat: Stat | None
    if stat_raw is None:
        stat = None
    else:
        if not isinstance(stat_raw, str):
            raise ValueError(f"invalid move {ref!r}: stat must be str or null")
        if not is_stat(stat_raw):
            raise ValueError(f"invalid move {ref!r}: stat must be one of {STATS}")
        stat = stat_raw

    trigger_raw = data["trigger"]
    if not isinstance(trigger_raw, str):
        raise ValueError(f"invalid move {ref!r}: trigger must be str")

    outcomes_raw = data["outcomes"]
    outcomes: Outcomes | None
    if outcomes_raw is None:
        outcomes = None
    else:
        if not isinstance(outcomes_raw, Mapping):
            raise ValueError(
                f"invalid move {ref!r}: outcomes must be a mapping or null"
            )
        outcomes_map = cast(Mapping[str, object], outcomes_raw)
        outcomes_mismatch = _key_mismatch_message(
            "move", ref, set(outcomes_map.keys()), _OUTCOMES_KEYS
        )
        if outcomes_mismatch is not None:
            raise ValueError(f"{outcomes_mismatch} (outcomes)")

        strong_hit_raw = outcomes_map["strong_hit"]
        if not isinstance(strong_hit_raw, str):
            raise ValueError(f"invalid move {ref!r}: outcomes.strong_hit must be str")

        weak_hit_raw = outcomes_map["weak_hit"]
        if not isinstance(weak_hit_raw, str):
            raise ValueError(f"invalid move {ref!r}: outcomes.weak_hit must be str")

        miss_raw = outcomes_map["miss"]
        miss: str | None
        if miss_raw is None:
            miss = None
        elif isinstance(miss_raw, str):
            miss = miss_raw
        else:
            raise ValueError(f"invalid move {ref!r}: outcomes.miss must be str or null")

        outcomes = Outcomes(strong_hit=strong_hit_raw, weak_hit=weak_hit_raw, miss=miss)

    body_markdown_raw = data["body_markdown"]
    if not isinstance(body_markdown_raw, str):
        raise ValueError(f"invalid move {ref!r}: body_markdown must be str")

    section_id_raw = data["section_id"]
    if not isinstance(section_id_raw, str):
        raise ValueError(f"invalid move {ref!r}: section_id must be str")

    return Move(
        id=id_raw,
        name=name_raw,
        category=category,
        class_=class_,
        stat=stat,
        trigger=trigger_raw,
        outcomes=outcomes,
        body_markdown=body_markdown_raw,
        section_id=section_id_raw,
    )


def section_from_dict(data: Mapping[str, object]) -> Section:
    if not hasattr(data, "get") or not hasattr(data, "keys"):
        raise ValueError("invalid section '?': expected a mapping")

    raw_id = data.get("id")
    ref = raw_id if isinstance(raw_id, str) else "?"

    mismatch = _key_mismatch_message("section", ref, set(data.keys()), _SECTION_KEYS)
    if mismatch is not None:
        raise ValueError(mismatch)

    id_raw = data["id"]
    if not isinstance(id_raw, str):
        raise ValueError(f"invalid section {ref!r}: id must be str")

    chapter_raw = data["chapter"]
    if not isinstance(chapter_raw, str):
        raise ValueError(f"invalid section {ref!r}: chapter must be str")

    title_raw = data["title"]
    if not isinstance(title_raw, str):
        raise ValueError(f"invalid section {ref!r}: title must be str")

    slug_raw = data["slug"]
    if not isinstance(slug_raw, str):
        raise ValueError(f"invalid section {ref!r}: slug must be str")

    parent_id_raw = data["parent_id"]
    parent_id: str | None
    if parent_id_raw is None:
        parent_id = None
    elif isinstance(parent_id_raw, str):
        parent_id = parent_id_raw
    else:
        raise ValueError(f"invalid section {ref!r}: parent_id must be str or null")

    order_raw = data["order"]
    if isinstance(order_raw, bool) or not isinstance(order_raw, int):
        raise ValueError(f"invalid section {ref!r}: order must be int, not bool")

    text_markdown_raw = data["text_markdown"]
    if not isinstance(text_markdown_raw, str):
        raise ValueError(f"invalid section {ref!r}: text_markdown must be str")

    return Section(
        id=id_raw,
        chapter=chapter_raw,
        title=title_raw,
        slug=slug_raw,
        parent_id=parent_id,
        order=order_raw,
        text_markdown=text_markdown_raw,
    )

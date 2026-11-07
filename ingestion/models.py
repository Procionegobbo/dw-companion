"""Frozen dataclasses mirroring the three committed `data/normalized/*.json` files.

Field order in each `to_dict()` is the field order the JSON is serialized in (see
`ingestion/pipeline.py`); it matches the *Data Model* tables in the spec exactly so the
committed snapshots are deterministic and reviewable in a diff.
"""

from dataclasses import dataclass
from typing import Literal

Category = Literal["basic", "special", "class"]
Stat = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA", "BOND", "VARIES", "NONE"]


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    chapter: str
    title: str
    slug: str
    parent_id: str | None
    order: int
    text_markdown: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "chapter": self.chapter,
            "title": self.title,
            "slug": self.slug,
            "parent_id": self.parent_id,
            "order": self.order,
            "text_markdown": self.text_markdown,
        }


@dataclass(frozen=True, slots=True)
class Outcomes:
    strong_hit: str
    weak_hit: str
    miss: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "strong_hit": self.strong_hit,
            "weak_hit": self.weak_hit,
            "miss": self.miss,
        }


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

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "class": self.class_,
            "stat": self.stat,
            "trigger": self.trigger,
            "outcomes": self.outcomes.to_dict() if self.outcomes is not None else None,
            "body_markdown": self.body_markdown,
            "section_id": self.section_id,
        }


@dataclass(frozen=True, slots=True)
class GameClass:
    id: str
    name: str
    section_id: str
    order: int
    max_hp_base: int
    base_damage: str
    load_base: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "section_id": self.section_id,
            "order": self.order,
            "max_hp_base": self.max_hp_base,
            "base_damage": self.base_damage,
            "load_base": self.load_base,
        }

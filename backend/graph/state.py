"""Turn input/output types and the LangGraph state shape (spec 006 Data Model).

`TurnInput` is validated at construction (D18); most other types here hold no
validation beyond what their own fields' types already guarantee, per the Data
Model's *Validation Rules* table (which lists no extra rules for them).
`NodeCompleted` (spec 008) is the one addition: its `node` must be non-empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Required, TypedDict

from backend.domain.dice import MAX_MODIFIER, MIN_MODIFIER, Band, Roll
from backend.domain.outcome import Outcome
from backend.domain.rulebook import AbilityStat, Move, Outcomes, Stat
from backend.graph.llm_outputs import Intent, MoveClassification
from backend.ports.retriever import RetrievedChunk

ReplyKind = Literal[
    "rules_answer",
    "rules_not_found",
    "move",
    "no_move",
    "clarification",
    "out_of_scope",
    "error",
]


@dataclass(frozen=True, slots=True)
class TurnInput:
    message: str
    session_id: str
    trace_id: str
    roll_requested: bool = False
    modifier: int | None = None

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("invalid TurnInput: message must be non-empty")
        if not self.session_id.strip():
            raise ValueError("invalid TurnInput: session_id must be non-empty")
        if not self.trace_id.strip():
            raise ValueError("invalid TurnInput: trace_id must be non-empty")
        if self.modifier is not None:
            if isinstance(self.modifier, bool):
                raise ValueError("invalid TurnInput: modifier must be an int, not bool")
            if self.modifier < MIN_MODIFIER or self.modifier > MAX_MODIFIER:
                raise ValueError(
                    "invalid TurnInput: modifier must be between "
                    f"{MIN_MODIFIER} and {MAX_MODIFIER}"
                )


@dataclass(frozen=True, slots=True)
class Citation:
    section_id: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class MoveCard:
    move_id: str
    name: str
    url: str
    trigger: str
    stat: Stat | None
    roll_stat: AbilityStat | None
    outcomes: Outcomes | None
    roll: Roll | None = None
    outcome: Outcome | None = None
    bands_by_modifier: tuple[tuple[int, Band], ...] = ()


@dataclass(frozen=True, slots=True)
class Reply:
    kind: ReplyKind
    text: str
    citations: tuple[Citation, ...] = ()
    move: MoveCard | None = None


@dataclass(frozen=True, slots=True)
class TurnResult:
    reply: Reply
    intent: Intent | None
    router_confidence: float | None
    classification: MoveClassification | None
    retrieved_section_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NodeCompleted:
    """One executed graph node, yielded by `Assistant.stream` (spec 008 D4)."""

    node: str

    def __post_init__(self) -> None:
        if not self.node.strip():
            raise ValueError("invalid NodeCompleted: node must be non-empty")


AssistantEvent = NodeCompleted | TurnResult


class GraphState(TypedDict, total=False):
    turn: Required[TurnInput]
    intent: Intent
    router_confidence: float
    chunks: tuple[RetrievedChunk, ...]
    draft_answer: str
    candidates: tuple[Move, ...]
    classification: MoveClassification
    move: Move
    roll_stat: AbilityStat | None
    roll: Roll
    reply: Reply

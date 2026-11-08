"""Dataset row types, the validating JSONL loader and the R-LABEL gate (spec 009).

`DatasetError` is raised for any schema problem in a dataset file, with a message
listing up to `MAX_ERROR_ITEMS` `"<file>:<line>: <problem>"` lines so every violation in
a file can be fixed in one pass. `ensure_reviewed` is rule R-LABEL (spec 009, points
1-3): it is the only gate that may stop a run for unreviewed rows, and it never
accepts anything other than JSON `true`. Nothing in this module ever writes
`"reviewed": true` to a file - only the project owner does that (rule R-LABEL point 2).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal, cast

from backend.adapters.retrieval.chunking import build_chunks
from backend.domain.rulebook import move_from_dict, section_from_dict
from backend.graph.llm_outputs import Intent

DatasetName = Literal["router", "rules_qa", "move_classification"]
DATASET_ORDER: Final[tuple[DatasetName, ...]] = (
    "router",
    "rules_qa",
    "move_classification",
)

MAX_MESSAGE_CHARS: Final = 500
MAX_KEY_FACTS: Final = 5
MAX_KEY_FACT_CHARS: Final = 300
MAX_ERROR_ITEMS: Final = 20
MAX_UNREVIEWED_IDS: Final = 10

_NO_MOVE: Final = "no_move"

_INTENTS: Final[frozenset[Intent]] = frozenset(
    {"rules_question", "action_description", "out_of_scope"}
)

_ID_PATTERNS: Final[Mapping[DatasetName, re.Pattern[str]]] = {
    "router": re.compile(r"^router-\d{3}$"),
    "rules_qa": re.compile(r"^rules-\d{3}$"),
    "move_classification": re.compile(r"^move-\d{3}$"),
}

_ROUTER_REQUIRED: Final = frozenset({"id", "message", "expected_intent"})
_ROUTER_ALLOWED: Final = _ROUTER_REQUIRED | {"reviewed"}
_RULES_REQUIRED: Final = frozenset(
    {"id", "message", "expected_section_ids", "key_facts"}
)
_RULES_ALLOWED: Final = _RULES_REQUIRED | {"reviewed"}
_MOVE_REQUIRED: Final = frozenset(
    {"id", "message", "expected_move_id", "acceptable_alternatives"}
)
_MOVE_ALLOWED: Final = _MOVE_REQUIRED | {"reviewed"}


class _RowError(Exception):
    """A single row's schema problem, raised without file/line context.

    `load_dataset` is the only place that attaches `"<file>:<line>:"` and collects
    every row's problem before raising `DatasetError`.
    """


@dataclass(frozen=True, slots=True)
class RouterCase:
    id: str
    message: str
    expected_intent: Intent
    reviewed: bool


@dataclass(frozen=True, slots=True)
class RulesCase:
    id: str
    message: str
    expected_section_ids: tuple[str, ...]
    key_facts: tuple[str, ...]
    reviewed: bool

    @property
    def answerable(self) -> bool:
        return len(self.expected_section_ids) > 0


@dataclass(frozen=True, slots=True)
class MoveCase:
    id: str
    message: str
    expected_move_id: str
    acceptable_alternatives: tuple[str, ...]
    reviewed: bool


Case = RouterCase | RulesCase | MoveCase


@dataclass(frozen=True, slots=True)
class Dataset:
    name: DatasetName
    path: Path
    sha256: str
    cases: tuple[Case, ...]


class DatasetError(Exception):
    """A dataset file failed schema validation (exit 2 in `evals/run.py`)."""


class UnreviewedRowsError(Exception):
    """Rule R-LABEL: a selected dataset has a row whose `reviewed` is not JSON `true`.

    `ids` holds at most `MAX_UNREVIEWED_IDS` offending ids; `count` is the true total.
    """

    def __init__(self, dataset: DatasetName, count: int, ids: tuple[str, ...]) -> None:
        shown = ", ".join(ids)
        suffix = ", ..." if count > len(ids) else ""
        super().__init__(
            f"dataset {dataset!r} has {count} unreviewed row(s): {shown}{suffix}"
        )
        self.dataset = dataset
        self.count = count
        self.ids = ids


@dataclass(frozen=True, slots=True)
class KnownIds:
    """Ids that the real rulebook data can actually produce (spec 009 D17)."""

    section_ids: frozenset[str]
    move_ids: frozenset[str]


def known_ids_from(normalized_dir: Path) -> KnownIds:
    """Section ids retrievable via `build_chunks` and move ids from `moves.json`.

    `move_ids` never contains `"no_move"`: that sentinel is not a real move and is
    validated separately wherever it is accepted alongside a known move id.
    """
    sections_raw = json.loads(
        (normalized_dir / "sections.json").read_text(encoding="utf-8")
    )
    moves_raw = json.loads((normalized_dir / "moves.json").read_text(encoding="utf-8"))
    sections = [section_from_dict(item) for item in sections_raw]
    moves = [move_from_dict(item) for item in moves_raw]
    chunks = build_chunks(sections, moves)
    section_ids = frozenset(chunk.section_id for chunk in chunks)
    move_ids = frozenset(move.id for move in moves)
    return KnownIds(section_ids=section_ids, move_ids=move_ids)


def _require_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise _RowError(f"{key} must be a string")
    return value


def _require_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise _RowError(f"{field_name} must be a list")
    items = cast(list[object], value)
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise _RowError(f"{field_name} entries must be strings")
        result.append(item)
    return result


def _check_keys(
    row: Mapping[str, object], required: frozenset[str], allowed: frozenset[str]
) -> None:
    keys = set(row.keys())
    missing = sorted(required - keys)
    extra = sorted(keys - allowed)
    if missing or extra:
        raise _RowError(f"missing keys {missing}, unexpected keys {extra}")


def _check_id(dataset: DatasetName, value: str) -> None:
    pattern = _ID_PATTERNS[dataset]
    if not pattern.fullmatch(value):
        raise _RowError(f"id {value!r} must match {pattern.pattern!r}")


def _check_message(value: str) -> None:
    if not value.strip():
        raise _RowError("message must be non-empty")
    if len(value) > MAX_MESSAGE_CHARS:
        raise _RowError(f"message must be at most {MAX_MESSAGE_CHARS} characters")


def _is_reviewed(row: Mapping[str, object]) -> bool:
    return row.get("reviewed") is True


def _parse_router_row(row: Mapping[str, object]) -> RouterCase:
    _check_keys(row, _ROUTER_REQUIRED, _ROUTER_ALLOWED)
    row_id = _require_str(row, "id")
    _check_id("router", row_id)
    message = _require_str(row, "message")
    _check_message(message)
    intent_raw = row.get("expected_intent")
    if not isinstance(intent_raw, str) or intent_raw not in _INTENTS:
        raise _RowError(f"expected_intent must be one of {sorted(_INTENTS)}")
    return RouterCase(
        id=row_id,
        message=message,
        expected_intent=intent_raw,
        reviewed=_is_reviewed(row),
    )


def _parse_rules_row(row: Mapping[str, object], known: KnownIds) -> RulesCase:
    _check_keys(row, _RULES_REQUIRED, _RULES_ALLOWED)
    row_id = _require_str(row, "id")
    _check_id("rules_qa", row_id)
    message = _require_str(row, "message")
    _check_message(message)

    section_ids = _require_str_list(
        row.get("expected_section_ids"), "expected_section_ids"
    )
    if len(set(section_ids)) != len(section_ids):
        raise _RowError("expected_section_ids must not contain duplicates")
    unknown_sections = sorted(set(section_ids) - known.section_ids)
    if unknown_sections:
        raise _RowError(f"unknown expected_section_ids: {unknown_sections}")

    key_facts = _require_str_list(row.get("key_facts"), "key_facts")
    if len(set(key_facts)) != len(key_facts):
        raise _RowError("key_facts must not contain duplicates")
    if len(key_facts) > MAX_KEY_FACTS:
        raise _RowError(f"key_facts must have at most {MAX_KEY_FACTS} entries")
    for fact in key_facts:
        if not fact.strip():
            raise _RowError("key_facts entries must be non-empty")
        if len(fact) > MAX_KEY_FACT_CHARS:
            raise _RowError(
                f"key_facts entries must be at most {MAX_KEY_FACT_CHARS} characters"
            )
    if bool(section_ids) != bool(key_facts):
        raise _RowError("key_facts must be empty iff expected_section_ids is empty")

    return RulesCase(
        id=row_id,
        message=message,
        expected_section_ids=tuple(section_ids),
        key_facts=tuple(key_facts),
        reviewed=_is_reviewed(row),
    )


def _parse_move_row(row: Mapping[str, object], known: KnownIds) -> MoveCase:
    _check_keys(row, _MOVE_REQUIRED, _MOVE_ALLOWED)
    row_id = _require_str(row, "id")
    _check_id("move_classification", row_id)
    message = _require_str(row, "message")
    _check_message(message)

    expected_move_id = _require_str(row, "expected_move_id")
    if expected_move_id != _NO_MOVE and expected_move_id not in known.move_ids:
        raise _RowError(f"unknown expected_move_id: {expected_move_id!r}")

    alternatives = _require_str_list(
        row.get("acceptable_alternatives"), "acceptable_alternatives"
    )
    if len(set(alternatives)) != len(alternatives):
        raise _RowError("acceptable_alternatives must not contain duplicates")
    unknown_alternatives = sorted(
        {alt for alt in alternatives if alt != _NO_MOVE and alt not in known.move_ids}
    )
    if unknown_alternatives:
        raise _RowError(f"unknown acceptable_alternatives: {unknown_alternatives}")
    if expected_move_id in alternatives:
        raise _RowError("acceptable_alternatives must not contain expected_move_id")

    return MoveCase(
        id=row_id,
        message=message,
        expected_move_id=expected_move_id,
        acceptable_alternatives=tuple(alternatives),
        reviewed=_is_reviewed(row),
    )


def _parse_row(name: DatasetName, row: Mapping[str, object], known: KnownIds) -> Case:
    if name == "router":
        return _parse_router_row(row)
    if name == "rules_qa":
        return _parse_rules_row(row, known)
    return _parse_move_row(row, known)


def _format_problems(problems: Sequence[str]) -> str:
    shown = problems[:MAX_ERROR_ITEMS]
    message = "\n".join(shown)
    remaining = len(problems) - len(shown)
    if remaining > 0:
        message += f"\n... and {remaining} more"
    return message


def load_dataset(name: DatasetName, path: Path, known: KnownIds) -> Dataset:
    """Parse and validate `path` as dataset `name`.

    Raises `DatasetError` listing every row's problem (up to `MAX_ERROR_ITEMS`), each
    as `"<file>:<line>: <problem>"`. A missing or non-boolean-`true` `reviewed` value is
    never a schema problem here - only `ensure_reviewed` (rule R-LABEL) acts on it.
    """
    text = path.read_text(encoding="utf-8")
    digest = sha256(text.encode("utf-8")).hexdigest()
    lines = text.splitlines()

    problems: list[str] = []
    cases: list[Case] = []
    seen_ids: set[str] = set()

    if not lines:
        problems.append(f"{path.name}:1: dataset file must contain at least one row")

    for lineno, line in enumerate(lines, start=1):
        if line.strip() == "":
            problems.append(f"{path.name}:{lineno}: blank line")
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}:{lineno}: invalid JSON ({exc})")
            continue
        if not isinstance(row, dict):
            problems.append(f"{path.name}:{lineno}: row must be a JSON object")
            continue
        try:
            case = _parse_row(name, cast(Mapping[str, object], row), known)
        except _RowError as exc:
            problems.append(f"{path.name}:{lineno}: {exc}")
            continue
        if case.id in seen_ids:
            problems.append(f"{path.name}:{lineno}: duplicate id {case.id!r}")
            continue
        seen_ids.add(case.id)
        cases.append(case)

    if problems:
        raise DatasetError(_format_problems(problems))

    return Dataset(name=name, path=path, sha256=digest, cases=tuple(cases))


def ensure_reviewed(dataset: Dataset) -> None:
    """Rule R-LABEL: raise `UnreviewedRowsError` unless every row's `reviewed is True`.

    There is no override. This is the drafting story's gate: `evals/run.py` (main) and
    `evals/runner.py` (`run_datasets`) each call it again before any network call, as
    two independent enforcement points (spec 009 D1).
    """
    unreviewed = tuple(case.id for case in dataset.cases if not case.reviewed)
    if not unreviewed:
        return
    raise UnreviewedRowsError(
        dataset.name, len(unreviewed), unreviewed[:MAX_UNREVIEWED_IDS]
    )

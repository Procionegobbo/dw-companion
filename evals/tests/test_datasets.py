"""Tests for `evals/datasets.py`: rule R-LABEL (`ensure_reviewed`) and the schema
loader (`load_dataset`, `known_ids_from`)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from hashlib import sha256
from pathlib import Path

import pytest

from backend.tests.adapter_helpers import mini_normalized
from evals.datasets import (
    Case,
    Dataset,
    DatasetError,
    DatasetName,
    KnownIds,
    RouterCase,
    RulesCase,
    UnreviewedRowsError,
    ensure_reviewed,
    known_ids_from,
    load_dataset,
)

from .helpers import move_row, router_row, rules_row, write_jsonl

EMPTY_KNOWN = KnownIds(section_ids=frozenset(), move_ids=frozenset())

_FIXTURE_MOVE_IDS = frozenset(
    {
        "hack-and-slash",
        "defy-danger",
        "volley",
        "discern-realities",
        "last-breath",
        "make-camp",
    }
)


def _router_case(id_: str, *, reviewed: bool) -> RouterCase:
    return RouterCase(
        id=id_, message="m", expected_intent="rules_question", reviewed=reviewed
    )


def _dataset(name: DatasetName, cases: Sequence[Case]) -> Dataset:
    return Dataset(
        name=name, path=Path(f"{name}.jsonl"), sha256="x", cases=tuple(cases)
    )


def test_ensure_reviewed_passes_when_all_true() -> None:
    dataset = _dataset(
        "router",
        [
            _router_case("router-001", reviewed=True),
            _router_case("router-002", reviewed=True),
        ],
    )
    ensure_reviewed(dataset)  # does not raise


def test_ensure_reviewed_rejects_false_row() -> None:
    dataset = _dataset(
        "router",
        [
            _router_case("router-001", reviewed=True),
            _router_case("router-002", reviewed=False),
            _router_case("router-003", reviewed=True),
        ],
    )
    with pytest.raises(UnreviewedRowsError) as exc_info:
        ensure_reviewed(dataset)
    error = exc_info.value
    assert error.count == 1
    assert error.ids == ("router-002",)
    assert "router" in str(error)


def _pop_reviewed(row: dict[str, object]) -> None:
    del row["reviewed"]


def _set_reviewed_string_true(row: dict[str, object]) -> None:
    row["reviewed"] = "true"


def _set_reviewed_one(row: dict[str, object]) -> None:
    row["reviewed"] = 1


def _set_reviewed_null(row: dict[str, object]) -> None:
    row["reviewed"] = None


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_pop_reviewed, id="missing_key"),
        pytest.param(_set_reviewed_string_true, id="string_true"),
        pytest.param(_set_reviewed_one, id="int_one"),
        pytest.param(_set_reviewed_null, id="json_null"),
    ],
)
def test_ensure_reviewed_rejects_missing_key_and_non_bool(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None]
) -> None:
    row = router_row("router-001", "A fine question", "rules_question")
    mutate(row)
    path = tmp_path / "router.jsonl"
    write_jsonl(path, [row])

    # Not a schema error: load_dataset succeeds.
    dataset = load_dataset("router", path, EMPTY_KNOWN)

    with pytest.raises(UnreviewedRowsError):
        ensure_reviewed(dataset)


def test_unreviewed_error_lists_at_most_ten_ids() -> None:
    cases = [_router_case(f"router-{i:03d}", reviewed=False) for i in range(1, 13)]
    dataset = _dataset("router", cases)
    with pytest.raises(UnreviewedRowsError) as exc_info:
        ensure_reviewed(dataset)
    error = exc_info.value
    assert error.count == 12
    assert len(error.ids) == 10


def test_load_valid_rows_each_dataset(tmp_path: Path) -> None:
    normalized_dir = mini_normalized(tmp_path)
    known = known_ids_from(normalized_dir)

    router_path = tmp_path / "router.jsonl"
    write_jsonl(
        router_path,
        [
            router_row(
                "router-001", "Can I Defy Danger to dodge this?", "rules_question"
            ),
            router_row(
                "router-002", "I swing my axe at the orc.", "action_description"
            ),
        ],
    )
    router_dataset = load_dataset("router", router_path, known)
    assert router_dataset.name == "router"
    assert router_dataset.path == router_path
    assert router_dataset.sha256 == sha256(router_path.read_bytes()).hexdigest()
    assert len(router_dataset.cases) == 2

    rules_path = tmp_path / "rules_qa.jsonl"
    write_jsonl(
        rules_path,
        [
            rules_row(
                "rules-001",
                "What happens when I take my Last Breath?",
                ["moves/last-breath"],
                ["You roll 2d6 with no stat added"],
            ),
            rules_row(
                "rules-002",
                "How many spell slots does a 5th-level wizard have?",
                [],
                [],
            ),
        ],
    )
    rules_dataset = load_dataset("rules_qa", rules_path, known)
    answerable, unanswerable = rules_dataset.cases
    assert isinstance(answerable, RulesCase)
    assert isinstance(unanswerable, RulesCase)
    assert answerable.answerable is True
    assert unanswerable.answerable is False

    move_path = tmp_path / "move_classification.jsonl"
    write_jsonl(
        move_path,
        [
            move_row(
                "move-001",
                "I swing my axe at the orc in front of me.",
                "hack-and-slash",
            ),
            move_row("move-002", "I just stand here quietly.", "no_move"),
        ],
    )
    move_dataset = load_dataset("move_classification", move_path, known)
    assert len(move_dataset.cases) == 2


def _unknown_key(_: KnownIds) -> list[object]:
    return [
        {**router_row("router-001", "Can I dodge?", "rules_question"), "foo": "bar"}
    ]


def _missing_message(_: KnownIds) -> list[object]:
    return [
        {"id": "router-001", "expected_intent": "rules_question", "reviewed": False}
    ]


def _empty_message(_: KnownIds) -> list[object]:
    return [router_row("router-001", "", "rules_question")]


def _long_message(_: KnownIds) -> list[object]:
    return [router_row("router-001", "x" * 501, "rules_question")]


def _duplicate_id(_: KnownIds) -> list[object]:
    return [
        router_row("router-001", "First message", "rules_question"),
        router_row("router-001", "Second message", "action_description"),
    ]


def _wrong_id_prefix(_: KnownIds) -> list[object]:
    return [router_row("rules-001", "Wrong prefix", "rules_question")]


def _unknown_intent(_: KnownIds) -> list[object]:
    return [router_row("router-001", "What intent is this?", "made_up_intent")]


def _unknown_section_id(_: KnownIds) -> list[object]:
    return [rules_row("rules-001", "A question", ["not/a/real/section"], ["a fact"])]


def _thanks_section_id(_: KnownIds) -> list[object]:
    return [rules_row("rules-001", "A question", ["thanks"], ["a fact"])]


def _key_facts_on_unanswerable(_: KnownIds) -> list[object]:
    return [rules_row("rules-001", "A question", [], ["a fact"])]


def _sections_without_key_facts(_: KnownIds) -> list[object]:
    return [rules_row("rules-001", "A question", ["moves/last-breath"], [])]


def _six_key_facts(_: KnownIds) -> list[object]:
    return [
        rules_row(
            "rules-001",
            "A question",
            ["moves/last-breath"],
            [f"fact {i}" for i in range(6)],
        )
    ]


def _unknown_move_id(_: KnownIds) -> list[object]:
    return [move_row("move-001", "I do something.", "not-a-real-move")]


def _alternative_equals_expected(_: KnownIds) -> list[object]:
    return [
        move_row("move-001", "I do something.", "hack-and-slash", ["hack-and-slash"])
    ]


def _duplicate_alternatives(_: KnownIds) -> list[object]:
    return [
        move_row(
            "move-001",
            "I do something.",
            "hack-and-slash",
            ["defy-danger", "defy-danger"],
        )
    ]


def _blank_line(_: KnownIds) -> list[object]:
    return [router_row("router-001", "A fine question", "rules_question"), ""]


def _empty_file(_: KnownIds) -> list[object]:
    return []


_SCHEMA_ERROR_CASES: tuple[
    tuple[str, DatasetName, Callable[[KnownIds], list[object]]], ...
] = (
    ("unknown key", "router", _unknown_key),
    ("missing message", "router", _missing_message),
    ("empty message", "router", _empty_message),
    ("501-character message", "router", _long_message),
    ("duplicate id", "router", _duplicate_id),
    ("wrong id prefix", "router", _wrong_id_prefix),
    ("unknown intent", "router", _unknown_intent),
    ("unknown section id", "rules_qa", _unknown_section_id),
    ("thanks section id (not a chunk)", "rules_qa", _thanks_section_id),
    ("key facts on an unanswerable row", "rules_qa", _key_facts_on_unanswerable),
    ("expected sections without key facts", "rules_qa", _sections_without_key_facts),
    ("six key facts", "rules_qa", _six_key_facts),
    ("unknown move id", "move_classification", _unknown_move_id),
    (
        "an alternative equal to the expected move id",
        "move_classification",
        _alternative_equals_expected,
    ),
    ("duplicate alternatives", "move_classification", _duplicate_alternatives),
    ("a blank line", "router", _blank_line),
    ("an empty file", "router", _empty_file),
)


@pytest.mark.parametrize(
    ("label", "dataset_name", "build"),
    _SCHEMA_ERROR_CASES,
    ids=[case[0] for case in _SCHEMA_ERROR_CASES],
)
def test_schema_errors(
    tmp_path: Path,
    label: str,
    dataset_name: DatasetName,
    build: Callable[[KnownIds], list[object]],
) -> None:
    normalized_dir = mini_normalized(tmp_path)
    known = known_ids_from(normalized_dir)
    rows = build(known)
    filename = f"{dataset_name}.jsonl"
    path = tmp_path / filename
    lines = ["" if row == "" else json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

    with pytest.raises(DatasetError) as exc_info:
        load_dataset(dataset_name, path, known)
    assert re.search(rf"{re.escape(filename)}:\d+", str(exc_info.value)), label


def test_known_ids_from_mini_normalized(tmp_path: Path) -> None:
    normalized_dir = mini_normalized(tmp_path)
    known = known_ids_from(normalized_dir)

    assert known.move_ids == _FIXTURE_MOVE_IDS
    assert "no_move" not in known.move_ids

    assert "moves/empty" not in known.section_ids
    assert "thanks" not in known.section_ids
    assert "moves" in known.section_ids
    assert "moves/hack-and-slash" in known.section_ids

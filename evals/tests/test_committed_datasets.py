"""Tests on the committed datasets under `evals/datasets/` (spec 009 story 2).

Read-only: this is the only test file allowed to read `evals/datasets/` (D16). It
exercises the real loader (`evals/datasets.py`) against `data/normalized/`, and checks
the drafting story's coverage requirements (*Dataset Drafting*). It is skipped, with
the stated reason, when `data/normalized/` has not been built yet (spec 002), since
ingestion output is not guaranteed to exist in every environment that runs the suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.datasets import (
    DATASET_ORDER,
    DatasetName,
    MoveCase,
    RouterCase,
    RulesCase,
    known_ids_from,
    load_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = REPO_ROOT / "evals" / "datasets"
NORMALIZED_DIR = REPO_ROOT / "data" / "normalized"

_SKIP_REASON = "data/normalized not built yet"

pytestmark = pytest.mark.skipif(
    not (NORMALIZED_DIR / "sections.json").exists(), reason=_SKIP_REASON
)

_BASIC_MOVE_IDS = frozenset(
    {
        "hack-and-slash",
        "volley",
        "defy-danger",
        "defend",
        "spout-lore",
        "discern-realities",
        "parley",
        "aid-or-interfere",
    }
)


def _raw_rows(name: DatasetName) -> list[dict[str, object]]:
    path = DATASETS_DIR / f"{name}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_committed_datasets_are_schema_valid() -> None:
    known = known_ids_from(NORMALIZED_DIR)
    for name in DATASET_ORDER:
        dataset = load_dataset(name, DATASETS_DIR / f"{name}.jsonl", known)
        assert len(dataset.cases) > 0

        for row in _raw_rows(name):
            assert "reviewed" in row, f"{name}: row {row.get('id')} missing reviewed"
            assert isinstance(row["reviewed"], bool), (
                f"{name}: row {row.get('id')} reviewed is not a JSON bool"
            )


def test_router_coverage() -> None:
    known = known_ids_from(NORMALIZED_DIR)
    dataset = load_dataset("router", DATASETS_DIR / "router.jsonl", known)

    assert len(dataset.cases) >= 40

    counts: dict[str, int] = {}
    for case in dataset.cases:
        assert isinstance(case, RouterCase)
        counts[case.expected_intent] = counts.get(case.expected_intent, 0) + 1

    assert set(counts) == {"rules_question", "action_description", "out_of_scope"}
    for intent, count in counts.items():
        assert count >= 8, f"intent {intent!r} has only {count} rows"


def test_rules_coverage() -> None:
    known = known_ids_from(NORMALIZED_DIR)
    dataset = load_dataset("rules_qa", DATASETS_DIR / "rules_qa.jsonl", known)

    assert len(dataset.cases) >= 40

    unanswerable = 0
    for case in dataset.cases:
        assert isinstance(case, RulesCase)
        if not case.answerable:
            unanswerable += 1
    assert unanswerable >= 8


def test_move_coverage() -> None:
    known = known_ids_from(NORMALIZED_DIR)
    dataset = load_dataset(
        "move_classification", DATASETS_DIR / "move_classification.jsonl", known
    )

    assert len(dataset.cases) >= 80

    move_cases: list[MoveCase] = []
    for case in dataset.cases:
        assert isinstance(case, MoveCase)
        move_cases.append(case)

    counts: dict[str, int] = {}
    for case in move_cases:
        counts[case.expected_move_id] = counts.get(case.expected_move_id, 0) + 1

    # Every one of the 21 real move ids is an expected_move_id at least once.
    assert known.move_ids <= counts.keys()
    assert len(known.move_ids) == 21

    for move_id in _BASIC_MOVE_IDS:
        assert counts.get(move_id, 0) >= 3, (
            f"{move_id} has only {counts.get(move_id, 0)} rows"
        )

    assert counts.get("no_move", 0) >= 15

    hack_defy_pairs = sum(
        1
        for case in move_cases
        if (
            case.expected_move_id == "hack-and-slash"
            and "defy-danger" in case.acceptable_alternatives
        )
        or (
            case.expected_move_id == "defy-danger"
            and "hack-and-slash" in case.acceptable_alternatives
        )
    )
    assert hack_defy_pairs >= 2

    lore_discern_pairs = sum(
        1
        for case in move_cases
        if (
            case.expected_move_id == "spout-lore"
            and "discern-realities" in case.acceptable_alternatives
        )
        or (
            case.expected_move_id == "discern-realities"
            and "spout-lore" in case.acceptable_alternatives
        )
    )
    assert lore_discern_pairs >= 2

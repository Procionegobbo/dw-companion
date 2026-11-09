"""Tests for `evals/config.py`: the TOML eval config loader."""

from __future__ import annotations

import dataclasses
from hashlib import sha256
from pathlib import Path

import pytest

from backend.graph.deps import GraphSettings
from evals.config import ConfigFileError, EvalConfig, EvalModels, load_config, model_env

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "evals" / "configs"

_VALID_MODELS = """
[models]
router = "m-router"
classifier = "m-classifier"
answer = "m-answer"
embeddings = "m-embeddings"
judge = "m-judge"
"""

_MISSING_JUDGE = """
[models]
router = "m-router"
classifier = "m-classifier"
answer = "m-answer"
embeddings = "m-embeddings"
"""

_EXTRA_MODEL_KEY = (
    _VALID_MODELS
    + """
extra = "nope"
"""
)

_JUDGE_EQUALS_ANSWER = """
[models]
router = "m-router"
classifier = "m-classifier"
answer = "m-answer"
embeddings = "m-embeddings"
judge = "M-ANSWER"
"""

_UNKNOWN_GRAPH_KEY = (
    _VALID_MODELS
    + """
[graph]
not_a_field = 1
"""
)

_RETRIEVAL_K_BOOL = (
    _VALID_MODELS
    + """
[graph]
retrieval_k = true
"""
)

_RETRIEVAL_K_ZERO = (
    _VALID_MODELS
    + """
[graph]
retrieval_k = 0
"""
)

_CLARIFY_THRESHOLD_OUT_OF_RANGE = (
    _VALID_MODELS
    + """
[graph]
clarify_threshold = 1.5
"""
)


def test_load_baseline_config() -> None:
    config = load_config("baseline", CONFIGS_DIR)
    assert config.name == "baseline"
    assert config.models.judge.casefold() != config.models.answer.casefold()
    assert config.graph.retrieval_k == 6
    expected_sha = sha256((CONFIGS_DIR / "baseline.toml").read_bytes()).hexdigest()
    assert config.sha256 == expected_sha


def test_graph_overrides_applied_and_defaults_kept(tmp_path: Path) -> None:
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "test.toml").write_text(
        _VALID_MODELS
        + """
[graph]
retrieval_k = 3
""",
        encoding="utf-8",
    )

    config = load_config("test", configs_dir)
    defaults = GraphSettings()

    assert config.graph.retrieval_k == 3
    assert config.graph.closest_sections_limit == defaults.closest_sections_limit
    assert config.graph.clarify_threshold == defaults.clarify_threshold
    assert config.graph.router_max_tokens == defaults.router_max_tokens
    assert config.graph.classifier_max_tokens == defaults.classifier_max_tokens
    assert config.graph.answer_max_tokens == defaults.answer_max_tokens
    assert config.graph.explain_max_tokens == defaults.explain_max_tokens
    assert config.graph.answer_temperature == defaults.answer_temperature


@pytest.mark.parametrize(
    ("name", "content"),
    [
        pytest.param("missing", None, id="missing_file"),
        pytest.param("test", "not valid toml [[", id="invalid_toml"),
        pytest.param("test", _MISSING_JUDGE, id="no_judge_model"),
        pytest.param("test", _EXTRA_MODEL_KEY, id="extra_model_key"),
        pytest.param(
            "test", _JUDGE_EQUALS_ANSWER, id="judge_equals_answer_case_insensitive"
        ),
        pytest.param("test", _UNKNOWN_GRAPH_KEY, id="unknown_graph_key"),
        pytest.param("test", _RETRIEVAL_K_BOOL, id="retrieval_k_is_bool"),
        pytest.param("test", _RETRIEVAL_K_ZERO, id="retrieval_k_is_zero"),
        pytest.param(
            "test", _CLARIFY_THRESHOLD_OUT_OF_RANGE, id="clarify_threshold_out_of_range"
        ),
        pytest.param("Base Line", _VALID_MODELS, id="invalid_name"),
    ],
)
def test_config_errors(tmp_path: Path, name: str, content: str | None) -> None:
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    if content is not None:
        (configs_dir / f"{name}.toml").write_text(content, encoding="utf-8")

    with pytest.raises(ConfigFileError):
        load_config(name, configs_dir)


def test_classifier_mini_config_differs_from_baseline_only_in_classifier() -> None:
    baseline = load_config("baseline", CONFIGS_DIR)
    candidate = load_config("classifier-mini", CONFIGS_DIR)

    assert candidate.models.classifier == "openai/gpt-4.1-mini"
    assert (
        dataclasses.replace(candidate.models, classifier=baseline.models.classifier)
        == baseline.models
    )
    assert candidate.models.judge == baseline.models.judge
    assert candidate.graph == baseline.graph


def test_model_env_maps_four_vars() -> None:
    config = EvalConfig(
        name="test",
        sha256="x",
        models=EvalModels(
            router="m-router",
            classifier="m-classifier",
            answer="m-answer",
            embeddings="m-embeddings",
            judge="m-judge",
        ),
        graph=GraphSettings(),
    )
    assert model_env(config) == {
        "MODEL_ROUTER": "m-router",
        "MODEL_CLASSIFIER": "m-classifier",
        "MODEL_ANSWER": "m-answer",
        "MODEL_EMBEDDINGS": "m-embeddings",
    }

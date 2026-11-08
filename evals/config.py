"""Eval config loader (spec 009 D6): a named `[models]` set plus optional `[graph]`
`GraphSettings` overrides, read from `evals/configs/<name>.toml` with stdlib
`tomllib`. The committed `baseline.toml` is the first config (spec 009
*Configuration*).
"""

from __future__ import annotations

import dataclasses
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final, cast

from backend.graph.deps import GraphSettings

NAME_PATTERN: Final = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

_MODEL_FIELDS: Final[tuple[str, ...]] = (
    "router",
    "classifier",
    "answer",
    "embeddings",
    "judge",
)
_TOP_LEVEL_ALLOWED: Final = frozenset({"models", "graph"})
_GRAPH_FIELD_NAMES: Final = frozenset(
    field.name for field in dataclasses.fields(GraphSettings)
)
_GRAPH_DEFAULTS: Final = GraphSettings()


def _is_float_field(name: str) -> bool:
    return isinstance(getattr(_GRAPH_DEFAULTS, name), float)


@dataclass(frozen=True, slots=True)
class EvalModels:
    router: str
    classifier: str
    answer: str
    embeddings: str
    judge: str


@dataclass(frozen=True, slots=True)
class EvalConfig:
    name: str
    sha256: str
    models: EvalModels
    graph: GraphSettings


class ConfigFileError(Exception):
    """A config file failed to load or validate (exit 2 in `evals/run.py`)."""


def _validate_models(
    data: Mapping[str, object], problems: list[str]
) -> EvalModels | None:
    models_raw = data.get("models")
    if not isinstance(models_raw, dict):
        problems.append("[models] must be a table")
        return None
    models = cast(Mapping[str, object], models_raw)

    model_keys = set(models.keys())
    missing = sorted(set(_MODEL_FIELDS) - model_keys)
    extra = sorted(model_keys - set(_MODEL_FIELDS))
    if missing:
        problems.append(f"[models] missing key(s): {missing}")
    if extra:
        problems.append(f"[models] unexpected key(s): {extra}")
    if missing or extra:
        return None

    values: dict[str, str] = {}
    for field_name in _MODEL_FIELDS:
        value = models[field_name]
        if (
            not isinstance(value, str)
            or not value.strip()
            or any(char.isspace() for char in value)
        ):
            problems.append(
                f"[models].{field_name} must be a non-empty string with no whitespace"
            )
            continue
        values[field_name] = value
    if len(values) != len(_MODEL_FIELDS):
        return None

    if values["judge"].casefold() == values["answer"].casefold():
        problems.append("judge model must differ from the answer model")
        return None

    return EvalModels(**values)


def _validate_graph(data: Mapping[str, object], problems: list[str]) -> GraphSettings:
    if "graph" not in data:
        return GraphSettings()

    graph_raw = data["graph"]
    if not isinstance(graph_raw, dict):
        problems.append("[graph] must be a table")
        return GraphSettings()
    graph = cast(Mapping[str, object], graph_raw)

    unknown = sorted(set(graph.keys()) - _GRAPH_FIELD_NAMES)
    if unknown:
        problems.append(f"[graph] unknown key(s): {unknown}")

    overrides: dict[str, object] = {}
    for key, value in graph.items():
        if key not in _GRAPH_FIELD_NAMES:
            continue
        if _is_float_field(key):
            if isinstance(value, bool) or not isinstance(value, int | float):
                problems.append(f"[graph].{key} must be a number")
                continue
            overrides[key] = float(value)
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                problems.append(f"[graph].{key} must be an integer")
                continue
            overrides[key] = value

    if problems:
        return GraphSettings()

    try:
        return dataclasses.replace(GraphSettings(), **overrides)
    except ValueError as exc:
        problems.append(str(exc))
        return GraphSettings()


def load_config(name: str, configs_dir: Path) -> EvalConfig:
    """Load and validate `evals/configs/<name>.toml`.

    Raises `ConfigFileError` listing every problem found (file errors, `[models]`
    shape, the judge-differs-from-answer rule, and `[graph]` overrides against
    `GraphSettings`' own validation).
    """
    if not NAME_PATTERN.fullmatch(name):
        raise ConfigFileError(
            f"invalid config name {name!r}: must match {NAME_PATTERN.pattern!r}"
        )

    path = configs_dir / f"{name}.toml"
    if not path.is_file():
        raise ConfigFileError(f"config file not found: {path}")

    text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigFileError(f"invalid TOML in {path.name}: {exc}") from exc

    problems: list[str] = []
    extra_top = sorted(set(data.keys()) - _TOP_LEVEL_ALLOWED)
    if extra_top:
        problems.append(f"unknown top-level key(s): {extra_top}")
    if "models" not in data:
        problems.append("missing required table [models]")
        models = None
    else:
        models = _validate_models(data, problems)

    graph = _validate_graph(data, problems)

    if problems or models is None:
        raise ConfigFileError("; ".join(problems))

    return EvalConfig(
        name=name,
        sha256=sha256(text.encode("utf-8")).hexdigest(),
        models=models,
        graph=graph,
    )


def model_env(config: EvalConfig) -> dict[str, str]:
    """The four `MODEL_*` env keys `Settings.from_env` reads (spec 007), from
    `config.models`. The judge model is not among them: it is wired separately
    through `build_eval_support`, never through `Settings`."""
    return {
        "MODEL_ROUTER": config.models.router,
        "MODEL_CLASSIFIER": config.models.classifier,
        "MODEL_ANSWER": config.models.answer,
        "MODEL_EMBEDDINGS": config.models.embeddings,
    }

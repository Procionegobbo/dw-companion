"""Tunable defaults and the dependency bundle nodes close over (D25).

`GraphSettings` fields are not env-configurable in this spec; spec 007's
composition root constructs `GraphDeps` with real adapters.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from backend.domain.dice import RandomSource
from backend.ports.llm import LLMClient
from backend.ports.retriever import Retriever
from backend.ports.rulebook import RulebookRepository
from backend.ports.tracer import Tracer

_INT_FIELDS: tuple[str, ...] = (
    "retrieval_k",
    "closest_sections_limit",
    "router_max_tokens",
    "classifier_max_tokens",
    "answer_max_tokens",
    "explain_max_tokens",
)


@dataclass(frozen=True, slots=True)
class GraphSettings:
    retrieval_k: int = 6
    closest_sections_limit: int = 3
    clarify_threshold: float = 0.6
    router_max_tokens: int = 100
    classifier_max_tokens: int = 400
    answer_max_tokens: int = 700
    explain_max_tokens: int = 300
    answer_temperature: float = 0.0

    def __post_init__(self) -> None:
        for field_name in _INT_FIELDS:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(
                    f"invalid GraphSettings: {field_name} must be an int >= 1"
                )
        if not (0.0 <= self.clarify_threshold <= 1.0):
            raise ValueError(
                "invalid GraphSettings: clarify_threshold must be between 0.0 and 1.0"
            )
        if not (0.0 <= self.answer_temperature <= 2.0):
            raise ValueError(
                "invalid GraphSettings: answer_temperature must be between 0.0 and 2.0"
            )


@dataclass(frozen=True, slots=True)
class GraphDeps:
    llm: LLMClient
    retriever: Retriever
    tracer: Tracer
    rulebook: RulebookRepository
    rng: RandomSource
    settings: GraphSettings = GraphSettings()
    clock: Callable[[], float] = time.perf_counter

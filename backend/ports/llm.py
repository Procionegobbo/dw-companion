"""The `LLMClient` port: one generic method over role-tagged requests (D3, D4).

Async because it does I/O. Prompts, schemas and output parsing live in `graph/`; the
adapter only maps `role` to a model name and calls the provider.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, Protocol

ModelRole = Literal["router", "classifier", "answer"]

_SCHEMA_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

_MIN_TEMPERATURE: Final = 0.0
_MAX_TEMPERATURE: Final = 2.0


@dataclass(frozen=True, slots=True)
class LLMRequest:
    role: ModelRole
    system: str
    user: str
    max_tokens: int
    temperature: float
    response_schema: Mapping[str, object] | None = None
    schema_name: str | None = None

    def __post_init__(self) -> None:
        if not self.system.strip():
            raise ValueError("invalid LLMRequest: system must be non-empty")
        if not self.user.strip():
            raise ValueError("invalid LLMRequest: user must be non-empty")
        if isinstance(self.max_tokens, bool) or self.max_tokens < 1:
            raise ValueError("invalid LLMRequest: max_tokens must be an int >= 1")
        if not math.isfinite(self.temperature):
            raise ValueError("invalid LLMRequest: temperature must be finite")
        if not (_MIN_TEMPERATURE <= self.temperature <= _MAX_TEMPERATURE):
            raise ValueError(
                "invalid LLMRequest: temperature must be between "
                f"{_MIN_TEMPERATURE} and {_MAX_TEMPERATURE}"
            )
        if (self.response_schema is None) != (self.schema_name is None):
            raise ValueError(
                "invalid LLMRequest: response_schema and schema_name must both be "
                "set or both be null"
            )
        if self.schema_name is not None and not _SCHEMA_NAME.fullmatch(
            self.schema_name
        ):
            raise ValueError(
                f"invalid LLMRequest: schema_name must match {_SCHEMA_NAME.pattern!r}"
            )


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("invalid LLMResponse: model must be non-empty")
        if isinstance(self.input_tokens, bool) or self.input_tokens < 0:
            raise ValueError("invalid LLMResponse: input_tokens must be an int >= 0")
        if isinstance(self.output_tokens, bool) or self.output_tokens < 0:
            raise ValueError("invalid LLMResponse: output_tokens must be an int >= 0")


class LLMClient(Protocol):
    async def generate(
        self, request: LLMRequest
    ) -> LLMResponse: ...  # raises PortError

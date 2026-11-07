"""Hand-written fake for the `LLMClient` port (spec 006 Testing)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.ports.errors import PortError
from backend.ports.llm import LLMRequest, LLMResponse, ModelRole


class FakeLLMClient:
    """Per-role FIFO queue of scripted response texts or `PortError`s.

    An exhausted queue raises `AssertionError` rather than blocking or returning
    something arbitrary, so a test that calls the LLM more times than it scripted
    fails loudly at the call site.
    """

    def __init__(
        self, responses: Mapping[ModelRole, Sequence[str | PortError]]
    ) -> None:
        self._queues: dict[ModelRole, list[str | PortError]] = {
            role: list(values) for role, values in responses.items()
        }
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        queue = self._queues.get(request.role, [])
        if not queue:
            raise AssertionError(f"unexpected {request.role} call")
        next_value = queue.pop(0)
        if isinstance(next_value, PortError):
            raise next_value
        return LLMResponse(
            text=next_value,
            model=f"fake-{request.role}",
            input_tokens=10,
            output_tokens=5,
        )

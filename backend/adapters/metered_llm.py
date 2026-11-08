"""Wraps an `LLMClient` port to report provider cost per completed call (spec 008 D12).

Imports only `backend.ports.*` and stdlib, so the budget-metering concern stays out
of the graph and the other adapters, which never know this wrapper exists.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final

from backend.ports.llm import LLMClient, LLMRequest, LLMResponse

logger = logging.getLogger("backend.adapters.metered_llm")

FALLBACK_CALL_COST_USD: Final = 0.01


class MeteredLLMClient:
    """Satisfies `ports.llm.LLMClient`; reports cost for every completed call.

    `on_cost` is invoked once per successful `generate`, with the provider's own
    `cost_usd` or, when that is `None`, `fallback_cost_usd`. A `PortError` from the
    inner client propagates without calling `on_cost`: failed calls count nothing.
    """

    def __init__(
        self,
        inner: LLMClient,
        on_cost: Callable[[float], None],
        fallback_cost_usd: float = FALLBACK_CALL_COST_USD,
    ) -> None:
        self._inner = inner
        self._on_cost = on_cost
        self._fallback_cost_usd = fallback_cost_usd
        self._warned = False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        response = await self._inner.generate(request)
        cost = response.cost_usd
        if cost is None:
            cost = self._fallback_cost_usd
            if not self._warned:
                self._warned = True
                logger.warning(
                    "LLM response had no cost; counting fallback %s USD",
                    self._fallback_cost_usd,
                )
        self._on_cost(cost)
        return response

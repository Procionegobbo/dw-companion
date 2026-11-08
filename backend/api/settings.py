"""Chat API environment settings and the constants `backend/api/` uses (spec 008
Configuration, D7-D14).

Parsed once by `create_app`, the same rule `backend.composition.Settings` follows:
adapters and the graph never read `os.environ` themselves. `create_app` wires
`rate_per_minute`/`rate_per_day`/`trusted_proxy_hops` into `backend/api/limits.py`'s
`RateLimiter`/`client_ip` and `daily_budget_usd` into its `SpendLedger`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from backend.composition import ConfigError

MAX_MESSAGE_CHARS: Final = 500
MAX_BODY_BYTES: Final = 16384
TURN_TIMEOUT_S: Final = 60.0
MAX_TRACKED_CLIENTS: Final = 10000

API_ENV_VARS: Final[tuple[str, ...]] = (
    "CHAT_RATE_PER_MINUTE",
    "CHAT_RATE_PER_DAY",
    "CHAT_DAILY_BUDGET_USD",
    "CHAT_TRUSTED_PROXY_HOPS",
)

_DEFAULT_RATE_PER_MINUTE: Final = 5
_DEFAULT_RATE_PER_DAY: Final = 50
_DEFAULT_DAILY_BUDGET_USD: Final = 1.0
_DEFAULT_TRUSTED_PROXY_HOPS: Final = 0

_MAX_BUDGET_USD: Final = 1000.0


@dataclass(frozen=True, slots=True)
class ApiSettings:
    rate_per_minute: int = _DEFAULT_RATE_PER_MINUTE
    rate_per_day: int = _DEFAULT_RATE_PER_DAY
    daily_budget_usd: float = _DEFAULT_DAILY_BUDGET_USD
    trusted_proxy_hops: int = _DEFAULT_TRUSTED_PROXY_HOPS

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> ApiSettings:
        def raw(name: str) -> str:
            return environ.get(name, "").strip()

        problems: list[str] = []

        def parse_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
            text = raw(name)
            if not text:
                return default
            try:
                parsed = int(text)
            except ValueError:
                parsed = None
            if parsed is None or parsed < minimum or parsed > maximum:
                problems.append(
                    f"{name} must be an integer between {minimum} and {maximum}"
                )
                return default
            return parsed

        rate_per_minute = parse_int(
            "CHAT_RATE_PER_MINUTE", _DEFAULT_RATE_PER_MINUTE, minimum=1, maximum=1000
        )
        rate_per_day = parse_int(
            "CHAT_RATE_PER_DAY", _DEFAULT_RATE_PER_DAY, minimum=1, maximum=100000
        )
        trusted_proxy_hops = parse_int(
            "CHAT_TRUSTED_PROXY_HOPS",
            _DEFAULT_TRUSTED_PROXY_HOPS,
            minimum=0,
            maximum=5,
        )

        daily_budget_usd = _DEFAULT_DAILY_BUDGET_USD
        budget_text = raw("CHAT_DAILY_BUDGET_USD")
        if budget_text:
            try:
                parsed_budget = float(budget_text)
            except ValueError:
                parsed_budget = None
            if (
                parsed_budget is None
                or not math.isfinite(parsed_budget)
                or not (0 < parsed_budget <= _MAX_BUDGET_USD)
            ):
                problems.append(
                    "CHAT_DAILY_BUDGET_USD must be a finite number greater than 0 "
                    f"and at most {_MAX_BUDGET_USD}"
                )
            else:
                daily_budget_usd = parsed_budget

        if problems:
            raise ConfigError("invalid configuration: " + "; ".join(problems))

        return cls(
            rate_per_minute=rate_per_minute,
            rate_per_day=rate_per_day,
            daily_budget_usd=daily_budget_usd,
            trusted_proxy_hops=trusted_proxy_hops,
        )

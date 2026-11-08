"""In-memory rate limiting and spend cap for `POST /api/chat` (spec 008 D9-D12,
Limits).

Per-process, never persisted (D9): a restart or a second instance each start
counting from zero. `RateLimiter` and `SpendLedger` take an injected `Clock`
(epoch seconds) so tests control time without real sleeps. `ClientKeyer` keeps raw
client IPs out of memory: only an HMAC-derived key is ever stored or looked up
(D11, D17).
"""

from __future__ import annotations

import hmac
import math
import secrets
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Final, Literal

from backend.api.settings import MAX_TRACKED_CLIENTS

Clock = Callable[[], float]

_SECONDS_PER_MINUTE: Final = 60
_KEY_HEX_LENGTH: Final = 32
_FORWARDED_HEADER: Final = "x-forwarded-for"


def _utc_date(now: float) -> date:
    return datetime.fromtimestamp(now, tz=UTC).date()


def seconds_until_utc_midnight(now: float) -> int:
    """Whole seconds from `now` to the next UTC midnight; ceiling, at least 1."""
    current = datetime.fromtimestamp(now, tz=UTC)
    midnight = datetime(current.year, current.month, current.day, tzinfo=UTC)
    next_midnight = midnight + timedelta(days=1)
    return max(1, math.ceil((next_midnight - current).total_seconds()))


def client_ip(headers: Mapping[str, str], peer_host: str | None, hops: int) -> str:
    """The client's IP per D11.

    With `hops <= 0`, the socket peer (`"unknown"` if none). Otherwise the `hops`-th
    `X-Forwarded-For` entry from the right, when at least that many non-empty
    entries are present; the socket peer otherwise. Header lookup is
    case-insensitive.
    """
    if hops <= 0:
        return peer_host or "unknown"

    forwarded: str | None = None
    for name, value in headers.items():
        if name.lower() == _FORWARDED_HEADER:
            forwarded = value
            break
    if forwarded is None:
        return peer_host or "unknown"

    parts = [part for part in (raw.strip() for raw in forwarded.split(",")) if part]
    if len(parts) < hops:
        return peer_host or "unknown"
    return parts[-hops]


class ClientKeyer:
    """Hides raw client IPs behind a per-process HMAC (D11, D17)."""

    def __init__(self, salt: bytes | None = None) -> None:
        self._salt = salt if salt is not None else secrets.token_bytes(16)

    def key(self, ip: str) -> str:
        digest = hmac.new(self._salt, ip.encode(), sha256).hexdigest()
        return digest[:_KEY_HEX_LENGTH]


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    scope: Literal["minute", "day"] | None
    retry_after_s: int | None


@dataclass
class _ClientState:
    day: date
    day_count: int = 0
    minute_times: list[float] = field(default_factory=list[float])


class RateLimiter:
    """Sliding 60s window plus a per-UTC-day count, per client key (D10).

    At most `max_clients` keys are kept; the least recently seen is evicted
    first. Only an allowed request is recorded: a rejected one does not count
    against either window (D8).
    """

    def __init__(
        self,
        per_minute: int,
        per_day: int,
        clock: Clock,
        max_clients: int = MAX_TRACKED_CLIENTS,
    ) -> None:
        self._per_minute = per_minute
        self._per_day = per_day
        self._clock = clock
        self._max_clients = max_clients
        self._clients: OrderedDict[str, _ClientState] = OrderedDict()

    def check(self, key: str) -> RateDecision:
        now = self._clock()
        today = _utc_date(now)
        stored = self._clients.get(key)

        day_count = (
            stored.day_count if stored is not None and stored.day == today else 0
        )
        if day_count >= self._per_day:
            return RateDecision(False, "day", seconds_until_utc_midnight(now))

        previous_times = stored.minute_times if stored is not None else []
        minute_times = [t for t in previous_times if t > now - _SECONDS_PER_MINUTE]
        if len(minute_times) >= self._per_minute:
            oldest = minute_times[0]
            retry_after = max(1, math.ceil(oldest + _SECONDS_PER_MINUTE - now))
            return RateDecision(False, "minute", retry_after)

        minute_times.append(now)
        self._clients[key] = _ClientState(
            day=today, day_count=day_count + 1, minute_times=minute_times
        )
        self._clients.move_to_end(key)
        while len(self._clients) > self._max_clients:
            self._clients.popitem(last=False)
        return RateDecision(True, None, None)


class SpendLedger:
    """Sum of recorded LLM costs for the current UTC day (D12)."""

    def __init__(self, daily_cap_usd: float, clock: Clock) -> None:
        self._cap = daily_cap_usd
        self._clock = clock
        self._day: date | None = None
        self._total = 0.0

    def _roll_if_new_day(self) -> None:
        today = _utc_date(self._clock())
        if self._day != today:
            self._day = today
            self._total = 0.0

    def record(self, cost_usd: float) -> None:
        if not math.isfinite(cost_usd) or cost_usd < 0:
            raise ValueError(
                "invalid SpendLedger.record: cost_usd must be finite and >= 0"
            )
        self._roll_if_new_day()
        self._total += cost_usd

    def spent_today(self) -> float:
        self._roll_if_new_day()
        return self._total

    def exhausted(self) -> bool:
        return self.spent_today() >= self._cap

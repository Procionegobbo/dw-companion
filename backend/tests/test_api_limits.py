"""Unit tests for `backend/api/limits.py` (spec 008 Testing).

Pure unit tests over `RateLimiter`, `SpendLedger`, `seconds_until_utc_midnight`,
`client_ip` and `ClientKeyer`, using `FakeClock` -- no HTTP, no graph.
"""

from __future__ import annotations

import pytest

from backend.api.limits import ClientKeyer, RateLimiter, SpendLedger, client_ip
from backend.api.limits import seconds_until_utc_midnight as until_midnight
from backend.tests.api_helpers import FakeClock


def test_minute_limit_allows_then_rejects() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=2, per_day=100, clock=clock)

    first = limiter.check("a")
    second = limiter.check("a")
    third = limiter.check("a")

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.scope == "minute"
    assert third.retry_after_s == 60


def test_minute_window_slides() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=1, per_day=100, clock=clock)

    limiter.check("a")
    clock.advance(30)
    rejected = limiter.check("a")
    assert rejected.allowed is False
    assert rejected.scope == "minute"
    assert rejected.retry_after_s == 30

    clock.advance(31)
    allowed = limiter.check("a")
    assert allowed.allowed is True


def test_day_limit_rejects_until_midnight() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=100, per_day=3, clock=clock)

    limiter.check("a")
    limiter.check("a")
    limiter.check("a")
    fourth = limiter.check("a")

    assert fourth.allowed is False
    assert fourth.scope == "day"
    assert fourth.retry_after_s == until_midnight(clock())


def test_day_resets_at_utc_midnight() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=100, per_day=1, clock=clock)

    limiter.check("a")
    rejected = limiter.check("a")
    assert rejected.allowed is False

    clock.advance(86400)
    allowed = limiter.check("a")
    assert allowed.allowed is True


def test_rejected_requests_not_counted() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=2, per_day=100, clock=clock)

    limiter.check("a")
    limiter.check("a")
    rejected = limiter.check("a")
    assert rejected.allowed is False

    clock.advance(60)
    assert limiter.check("a").allowed is True
    assert limiter.check("a").allowed is True
    assert limiter.check("a").allowed is False


def test_keys_are_independent() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=1, per_day=100, clock=clock)

    assert limiter.check("a").allowed is True
    rejected_a = limiter.check("a")
    assert rejected_a.allowed is False
    assert rejected_a.scope == "minute"

    assert limiter.check("b").allowed is True


def test_least_recent_client_evicted() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=100, per_day=1, clock=clock, max_clients=2)

    assert limiter.check("a").allowed is True
    assert limiter.check("b").allowed is True
    assert limiter.check("c").allowed is True  # evicts the least recently seen: "a"

    # "a" was forgotten, so its day count reset to 0; without eviction this call
    # would be rejected (per_day=1, already used once).
    assert limiter.check("a").allowed is True


def test_seconds_until_utc_midnight() -> None:
    assert until_midnight(1_767_225_599.5) == 1
    assert until_midnight(1_767_225_600.0) == 86400


def test_spend_ledger_accumulates_and_exhausts() -> None:
    clock = FakeClock()
    ledger = SpendLedger(0.05, clock)

    ledger.record(0.02)
    ledger.record(0.02)
    assert ledger.exhausted() is False

    ledger.record(0.01)
    assert ledger.exhausted() is True


def test_spend_ledger_resets_next_utc_day() -> None:
    clock = FakeClock()
    ledger = SpendLedger(0.01, clock)

    ledger.record(0.01)
    assert ledger.exhausted() is True

    clock.advance(86400)
    assert ledger.exhausted() is False
    assert ledger.spent_today() == 0.0


@pytest.mark.parametrize("bad_cost", [-0.01, float("nan")])
def test_spend_ledger_rejects_invalid_cost(bad_cost: float) -> None:
    ledger = SpendLedger(1.0, FakeClock())
    with pytest.raises(ValueError, match="finite"):
        ledger.record(bad_cost)


@pytest.mark.parametrize(
    ("headers", "peer_host", "hops", "expected"),
    [
        ({}, "1.2.3.4", 0, "1.2.3.4"),
        ({"X-Forwarded-For": "1.1.1.1, 2.2.2.2"}, "9.9.9.9", 1, "2.2.2.2"),
        ({"X-Forwarded-For": "1.1.1.1, 2.2.2.2"}, "9.9.9.9", 2, "1.1.1.1"),
        ({}, "9.9.9.9", 1, "9.9.9.9"),
        ({"X-Forwarded-For": "1.1.1.1, 2.2.2.2"}, "9.9.9.9", 3, "9.9.9.9"),
        ({}, None, 1, "unknown"),
        ({"x-forwarded-for": "1.1.1.1, 2.2.2.2"}, "9.9.9.9", 1, "2.2.2.2"),
    ],
)
def test_client_ip_cases(
    headers: dict[str, str], peer_host: str | None, hops: int, expected: str
) -> None:
    assert client_ip(headers, peer_host, hops) == expected


def test_client_keyer_hides_ip() -> None:
    keyer = ClientKeyer(b"salt-one")
    other_keyer = ClientKeyer(b"salt-two")

    key = keyer.key("203.0.113.7")

    assert len(key) == 32
    assert all(c in "0123456789abcdef" for c in key)
    assert key != "203.0.113.7"
    assert keyer.key("203.0.113.7") == key
    assert other_keyer.key("203.0.113.7") != key

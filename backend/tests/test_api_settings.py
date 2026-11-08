"""Tests for `backend/api/settings.py` (spec 008 Testing)."""

from __future__ import annotations

import pytest

from backend.api.settings import API_ENV_VARS, ApiSettings
from backend.composition import REPO_ROOT, ConfigError


def test_defaults_when_unset() -> None:
    settings = ApiSettings.from_env({})

    assert settings == ApiSettings(
        rate_per_minute=5, rate_per_day=50, daily_budget_usd=1.0, trusted_proxy_hops=0
    )


def test_valid_values_parsed() -> None:
    settings = ApiSettings.from_env(
        {"CHAT_RATE_PER_MINUTE": " 7 ", "CHAT_DAILY_BUDGET_USD": "2.50"}
    )

    assert settings.rate_per_minute == 7
    assert settings.daily_budget_usd == 2.5


def test_invalid_values_listed_together() -> None:
    env = {
        "CHAT_RATE_PER_MINUTE": "x",
        "CHAT_DAILY_BUDGET_USD": "0",
        "CHAT_TRUSTED_PROXY_HOPS": "9",
    }

    with pytest.raises(ConfigError) as exc_info:
        ApiSettings.from_env(env)

    message = str(exc_info.value)
    assert message.startswith("invalid configuration: ")
    for name in (
        "CHAT_RATE_PER_MINUTE",
        "CHAT_DAILY_BUDGET_USD",
        "CHAT_TRUSTED_PROXY_HOPS",
    ):
        assert name in message


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_budget_rejects_nan_and_inf(value: str) -> None:
    with pytest.raises(ConfigError, match="CHAT_DAILY_BUDGET_USD"):
        ApiSettings.from_env({"CHAT_DAILY_BUDGET_USD": value})


def test_env_example_declares_api_settings() -> None:
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0]
        for line in env_example.splitlines()
        if line and not line.startswith("#") and "=" in line
    }

    for name in API_ENV_VARS:
        assert name in keys

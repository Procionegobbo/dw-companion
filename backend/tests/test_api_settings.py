"""Tests for `backend/api/settings.py` (spec 008 Testing)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.api.settings import API_ENV_VARS, ApiSettings
from backend.composition import REPO_ROOT, ConfigError


def make_site(tmp_path: Path) -> Path:
    """Writes spec 011's shared site fixture under `tmp_path` and returns `site/`."""
    site = tmp_path / "site"
    (site / "rules" / "x").mkdir(parents=True)
    (site / "index.html").write_text("<p>home</p>", encoding="utf-8")
    (site / "rules" / "x" / "index.html").write_text("<p>rule x</p>", encoding="utf-8")
    (site / "404.html").write_text("<p>missing</p>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return site


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


@pytest.mark.parametrize("env", [{}, {"SITE_DIR": "  "}])
def test_site_dir_unset_is_none(env: dict[str, str]) -> None:
    settings = ApiSettings.from_env(env)

    assert settings.site_dir is None


def test_site_dir_parsed_and_resolved(tmp_path: Path) -> None:
    site = make_site(tmp_path)

    settings = ApiSettings.from_env({"SITE_DIR": str(site)})

    assert settings.site_dir == site.resolve()


def test_site_dir_must_contain_index(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    empty = tmp_path / "empty"
    empty.mkdir()

    for bad_dir in (missing, empty):
        with pytest.raises(ConfigError) as exc_info:
            ApiSettings.from_env({"SITE_DIR": str(bad_dir)})
        assert "SITE_DIR must be a directory containing index.html" in str(
            exc_info.value
        )

    with pytest.raises(ConfigError) as exc_info:
        ApiSettings.from_env({"SITE_DIR": str(missing), "CHAT_RATE_PER_MINUTE": "0"})

    message = str(exc_info.value)
    assert "SITE_DIR must be a directory containing index.html" in message
    assert "CHAT_RATE_PER_MINUTE" in message


def test_env_example_declares_api_settings() -> None:
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0]
        for line in env_example.splitlines()
        if line and not line.startswith("#") and "=" in line
    }

    for name in API_ENV_VARS:
        assert name in keys

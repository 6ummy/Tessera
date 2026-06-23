"""Alpaca PAPER broker — guard tests (no network). Proves it refuses to
construct unless explicitly enabled AND pointed at the paper endpoint."""

from __future__ import annotations

import pytest

from tessera_worker.config import Settings
from tessera_worker.execution.alpaca_broker import AlpacaBroker
from tessera_worker.execution.broker import LiveTradingNotCleared


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "feature_alpaca_paper_execution": True,
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "alpaca_api_key": "k",
        "alpaca_api_secret": "s",
    }
    base.update(over)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_refuses_when_flag_off() -> None:
    with pytest.raises(LiveTradingNotCleared):
        AlpacaBroker(_settings(feature_alpaca_paper_execution=False))


def test_refuses_non_paper_endpoint() -> None:
    # The crucial guard: a real-money base URL is rejected outright.
    with pytest.raises(LiveTradingNotCleared, match="paper"):
        AlpacaBroker(_settings(alpaca_base_url="https://api.alpaca.markets"))


def test_refuses_without_credentials() -> None:
    with pytest.raises(LiveTradingNotCleared):
        AlpacaBroker(_settings(alpaca_api_key="", alpaca_api_secret=""))


def test_constructs_when_enabled_and_paper() -> None:
    # Constructing is offline (no API call until a method runs).
    broker = AlpacaBroker(_settings())
    assert broker.is_live is True
    assert "paper-api.alpaca.markets" in broker._base

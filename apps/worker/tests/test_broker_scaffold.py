"""Phase F broker scaffolding — proves live trading CANNOT execute from the
broker layer under the pilot's defaults (defense in depth)."""

from __future__ import annotations

import pytest

from tessera_worker.config import Settings
from tessera_worker.execution.broker import (
    LiveBroker,
    LiveTradingNotCleared,
    OrderIntent,
    PaperBroker,
    get_broker,
)


def _settings(**over: bool) -> Settings:
    return Settings(_env_file=None, **over)  # type: ignore[call-arg]


def test_get_broker_is_paper_by_default() -> None:
    broker = get_broker(_settings())
    assert isinstance(broker, PaperBroker)
    assert broker.is_live is False


def test_get_broker_paper_even_if_only_one_flag_set() -> None:
    # A single flag must NOT be enough to select the live broker.
    assert isinstance(get_broker(_settings(feature_live_trading=True)), PaperBroker)
    assert isinstance(get_broker(_settings(feature_live_trading_cleared=True)), PaperBroker)


def test_paper_broker_accepts_without_real_money() -> None:
    res = PaperBroker().place_order(OrderIntent("AAPL", "buy", 1))
    assert res.accepted and res.broker_order_id is None and res.detail == "paper"


def test_live_broker_refuses_when_flags_off() -> None:
    lb = LiveBroker(_settings())
    with pytest.raises(LiveTradingNotCleared):
        lb.place_order(OrderIntent("AAPL", "buy", 1, confirm_token="x"))
    with pytest.raises(LiveTradingNotCleared):
        lb.cancel_all()


def test_live_broker_refuses_without_compliance_gate() -> None:
    lb = LiveBroker(_settings(feature_live_trading=True))  # only the first flag
    with pytest.raises(LiveTradingNotCleared):
        lb.place_order(OrderIntent("AAPL", "buy", 1, confirm_token="x"))


def test_live_broker_refuses_order_without_confirm_token() -> None:
    lb = LiveBroker(_settings(feature_live_trading=True, feature_live_trading_cleared=True))
    with pytest.raises(LiveTradingNotCleared):
        lb.place_order(OrderIntent("AAPL", "buy", 1))  # no confirm_token


def test_live_broker_is_stub_even_when_fully_gated() -> None:
    # Both flags + a confirm token → passes the gates but is STILL a stub:
    # no real order can be placed from this scaffolding.
    lb = LiveBroker(_settings(feature_live_trading=True, feature_live_trading_cleared=True))
    with pytest.raises(NotImplementedError):
        lb.place_order(OrderIntent("AAPL", "buy", 1, confirm_token="confirmed"))

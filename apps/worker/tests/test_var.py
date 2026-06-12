"""Parametric VaR + drawdown math tests (risk/var.py pure core)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from tessera_worker.risk.var import (
    Z_99,
    align_log_returns,
    current_drawdown,
    parametric_var99,
)


def _dates(n: int) -> list[date]:
    start = date(2025, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def test_align_intersects_calendars():
    """Crypto trades weekends, equities don't — covariance needs every
    return vector on the same clock, so alignment intersects dates."""
    days = _dates(5)
    closes = {
        "AAPL": {days[0]: 100.0, days[1]: 101.0, days[3]: 102.0, days[4]: 103.0},
        "BTC/USD": {d: 50_000.0 + i for i, d in enumerate(days)},  # all 5 days
    }
    returns = align_log_returns(closes)
    # common dates = AAPL's 4 → 3 returns each, equal lengths
    assert len(returns["AAPL"]) == len(returns["BTC/USD"]) == 3


def test_var99_single_asset_matches_closed_form():
    """One asset: VaR99 = z99 × w × σ. Pin against a hand computation."""
    rets = [0.01, -0.02, 0.015, -0.005, 0.0] * 20  # 100 obs
    mean = sum(rets) / len(rets)
    sigma = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    var = parametric_var99({"AAPL": 0.5}, {"AAPL": rets})
    assert var == pytest.approx(Z_99 * 0.5 * sigma, rel=1e-9)


def test_var99_diversification_reduces_risk():
    """Two perfectly anti-correlated assets at equal weight ≈ zero VaR;
    the same gross in one asset is strictly riskier."""
    a = [0.01, -0.01] * 50
    b = [-0.01, 0.01] * 50
    hedged = parametric_var99({"A": 0.3, "B": 0.3}, {"A": a, "B": b})
    concentrated = parametric_var99({"A": 0.6}, {"A": a})
    assert hedged is not None and concentrated is not None
    assert hedged == pytest.approx(0.0, abs=1e-9)
    assert concentrated > 0.01


def test_var99_insufficient_history_returns_none():
    assert parametric_var99({"NEW": 0.2}, {"NEW": [0.01] * 30}) is None
    assert parametric_var99({"X": 0.2}, {}) is None
    assert parametric_var99({}, {"A": [0.01] * 100}) is None


def test_current_drawdown():
    assert current_drawdown([100.0]) is None
    assert current_drawdown([100.0, 110.0, 120.0]) == pytest.approx(0.0)
    assert current_drawdown([100.0, 120.0, 90.0]) == pytest.approx(0.25)

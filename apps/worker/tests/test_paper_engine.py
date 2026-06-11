"""Paper engine math tests — the pure core, no DB.

NAV conservation is THE invariant: the engine models no commissions or
slippage, so cash + Σ(qty × price) must be identical before and after
any rebalance. If these tests fail, the paper P&L track is fiction.
"""

from __future__ import annotations

import pytest

from tessera_worker.risk.paper_engine import (
    INITIAL_CAPITAL_USD,
    book_to_targets,
    compute_rebalance,
    mark_to_market,
    max_drawdown,
    sharpe_30d,
)


def _nav(positions: dict[str, float], cash: float, prices: dict[str, float]) -> float:
    return cash + sum(q * prices[t] for t, q in positions.items())


# ── compute_rebalance ────────────────────────────────────────────────────

def test_bootstrap_buys_from_all_cash():
    prices = {"AAPL": 200.0, "JPM": 250.0}
    fills, positions, cash = compute_rebalance(
        {}, INITIAL_CAPITAL_USD,
        {"AAPL": 0.15, "JPM": 0.10},
        prices,
    )
    assert {f.ticker: f.side for f in fills} == {"AAPL": "buy", "JPM": "buy"}
    assert positions["AAPL"] * 200.0 == pytest.approx(15_000.0)
    assert positions["JPM"] * 250.0 == pytest.approx(10_000.0)
    assert cash == pytest.approx(75_000.0)
    assert _nav(positions, cash, prices) == pytest.approx(INITIAL_CAPITAL_USD)


def test_weight_reduction_sells_and_conserves_nav():
    prices = {"AAPL": 200.0}
    start_positions = {"AAPL": 100.0}      # $20K position
    start_cash = 80_000.0
    fills, positions, cash = compute_rebalance(
        start_positions, start_cash, {"AAPL": 0.05}, prices,
    )
    assert len(fills) == 1 and fills[0].side == "sell"
    assert positions["AAPL"] * 200.0 == pytest.approx(5_000.0)
    assert _nav(positions, cash, prices) == pytest.approx(
        _nav(start_positions, start_cash, prices))


def test_dropped_target_liquidates_fully():
    prices = {"AAPL": 200.0}
    fills, positions, cash = compute_rebalance(
        {"AAPL": 50.0}, 90_000.0, {}, prices,
    )
    assert fills[0].side == "sell" and fills[0].qty == pytest.approx(50.0)
    assert positions == {}
    assert cash == pytest.approx(100_000.0)


def test_dust_rebalance_is_skipped():
    """A sub-$1 diff must not generate a trade — ledger readability."""
    prices = {"AAPL": 200.0}
    # current 15.0% vs target 15.0000001% → diff well under MIN_TRADE_USD
    positions = {"AAPL": 75.0}  # exactly 15% of 100K
    fills, new_positions, cash = compute_rebalance(
        positions, 85_000.0, {"AAPL": 0.150000001}, prices,
    )
    assert fills == []
    assert new_positions == positions


def test_fractional_shares_allowed():
    prices = {"BRK.B": 730.0}
    fills, positions, _cash = compute_rebalance(
        {}, INITIAL_CAPITAL_USD, {"BRK.B": 0.10}, prices,
    )
    assert positions["BRK.B"] == pytest.approx(10_000.0 / 730.0)
    assert fills[0].qty == positions["BRK.B"]


# ── mark_to_market ───────────────────────────────────────────────────────

def test_mark_to_market():
    total = mark_to_market({"AAPL": 10.0, "JPM": 4.0}, 1_000.0,
                           {"AAPL": 200.0, "JPM": 250.0})
    assert total == pytest.approx(1_000.0 + 2_000.0 + 1_000.0)


# ── performance math ─────────────────────────────────────────────────────

def test_sharpe_requires_five_observations():
    assert sharpe_30d([0.01, 0.02]) is None
    assert sharpe_30d([0.01] * 5) is None       # zero variance → None
    assert sharpe_30d([0.01, -0.005, 0.02, 0.0, 0.01]) is not None


def test_sharpe_sign_follows_mean_return():
    up = sharpe_30d([0.01, 0.02, 0.005, 0.015, 0.01])
    down = sharpe_30d([-0.01, -0.02, -0.005, -0.015, -0.01])
    assert up is not None and up > 0
    assert down is not None and down < 0


def test_max_drawdown():
    assert max_drawdown([100.0]) is None
    assert max_drawdown([100.0, 110.0, 120.0]) == pytest.approx(0.0)
    # peak 120 → trough 90 = 25% drawdown
    assert max_drawdown([100.0, 120.0, 90.0, 105.0]) == pytest.approx(0.25)


# ── book_to_targets ──────────────────────────────────────────────────────

def test_book_to_targets_stock_picker():
    parsed = {
        "cash_target": 0.30,
        "proposals": [
            {"ticker": "AAPL", "target_weight": 0.15},
            {"ticker": "MSFT", "target_weight": 0.0},     # watchlist → out
            {"ticker": None, "target_weight": 0.10},       # malformed → out
        ],
    }
    assert book_to_targets(parsed) == {"AAPL": 0.15}


def test_book_to_targets_ray_allocations():
    parsed = {
        "allocations": [
            {"instrument": "VTI", "target_weight": 0.40},
            {"instrument": "GLD", "target_weight": 0.20},
        ],
    }
    assert book_to_targets(parsed) == {"VTI": 0.40, "GLD": 0.20}

"""Persona → Alpaca paper mirror — pure rebalance diff (no network/DB)."""

from __future__ import annotations

from tessera_worker.execution.mirror_live import compute_rebalance


def _by_ticker(lines):
    return {ln.ticker: ln for ln in lines}


def test_buys_to_reach_target_from_empty() -> None:
    # 50% AAPL of $10k equity at $100 = $5k = 50 shares, from 0.
    lines = _by_ticker(compute_rebalance({"AAPL": 0.5}, {"AAPL": 100.0}, {}, 10_000))
    ln = lines["AAPL"]
    assert ln.target_qty == 50.0 and ln.side == "buy" and ln.trade_qty == 50.0


def test_exits_a_holding_not_in_target() -> None:
    # Hold 10 TSLA, target weight 0 → sell all 10.
    lines = _by_ticker(compute_rebalance(
        {"AAPL": 1.0}, {"AAPL": 100.0, "TSLA": 50.0}, {"TSLA": 10.0}, 10_000))
    assert lines["TSLA"].side == "sell" and lines["TSLA"].trade_qty == 10.0


def test_already_in_sync_is_noop() -> None:
    # 100% AAPL of $10k at $100 = 100 shares, already holding 100.
    lines = _by_ticker(compute_rebalance({"AAPL": 1.0}, {"AAPL": 100.0}, {"AAPL": 100.0}, 10_000))
    assert lines["AAPL"].side is None and lines["AAPL"].trade_qty == 0.0


def test_trims_an_overweight_position() -> None:
    # Target 30 shares, holding 50 → sell 20.
    lines = _by_ticker(compute_rebalance({"AAPL": 0.3}, {"AAPL": 100.0}, {"AAPL": 50.0}, 10_000))
    assert lines["AAPL"].side == "sell" and lines["AAPL"].trade_qty == 20.0


def test_skips_sub_min_notional_adjustment() -> None:
    # Target 100 shares, holding 100 already → no trade (and a $1 wobble is skipped).
    lines = _by_ticker(compute_rebalance(
        {"AAPL": 1.0}, {"AAPL": 100.0}, {"AAPL": 100.0}, 10_005, min_notional=50.0))
    assert lines["AAPL"].side is None  # round(100.05) == 100, delta 0

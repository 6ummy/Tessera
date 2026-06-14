"""Paper engine math tests — the pure core, no DB.

NAV conservation is THE invariant: the engine models no commissions or
slippage, so cash + Σ(qty × price) must be identical before and after
any rebalance. If these tests fail, the paper P&L track is fiction.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from tessera_worker.risk.paper_engine import (
    INITIAL_CAPITAL_USD,
    REFUSE_WRITE_STALE_DAYS,
    TradeRecord,
    book_to_targets,
    closed_lots_hit_rate,
    compute_rebalance,
    mark_to_market,
    max_drawdown,
    sharpe_30d,
    validate_bars,
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


# ── validate_bars (data integrity gate) ─────────────────────────────────


def test_validate_bars_passes_on_fresh_finite_prices():
    today = _dt.date(2026, 6, 14)
    bars = {
        "AAPL": (today,                              210.0, 215.0),
        "JPM":  (today - _dt.timedelta(days=3),      255.0, 258.0),
    }
    held = {"AAPL", "JPM"}
    r = validate_bars(bars, held, today)
    assert r.ok
    assert r.reasons == []
    assert r.stale_tickers == []
    assert r.invalid_tickers == []


def test_validate_bars_flags_missing_held_ticker():
    today = _dt.date(2026, 6, 14)
    bars = {"AAPL": (today, 210.0, 215.0)}
    r = validate_bars(bars, {"AAPL", "JPM"}, today)
    assert not r.ok
    assert any("JPM" in s for s in r.reasons)


def test_validate_bars_refuses_stale_held_position():
    today = _dt.date(2026, 6, 14)
    stale_date = today - _dt.timedelta(days=REFUSE_WRITE_STALE_DAYS + 1)
    bars = {"AAPL": (stale_date, 210.0, 215.0)}
    r = validate_bars(bars, {"AAPL"}, today)
    assert not r.ok
    assert "AAPL" in r.stale_tickers


def test_validate_bars_flags_non_finite_close():
    today = _dt.date(2026, 6, 14)
    bars = {"AAPL": (today, 210.0, float("nan"))}
    r = validate_bars(bars, {"AAPL"}, today)
    assert not r.ok
    assert "AAPL" in r.invalid_tickers


def test_validate_bars_flags_zero_or_negative_price():
    today = _dt.date(2026, 6, 14)
    bars = {
        "AAPL": (today, 210.0, 0.0),
        "JPM":  (today, 250.0, -1.0),
    }
    r = validate_bars(bars, {"AAPL", "JPM"}, today)
    assert not r.ok
    assert set(r.invalid_tickers) == {"AAPL", "JPM"}


def test_validate_bars_ignores_non_held_ticker_staleness():
    """A stale bar for a ticker we don't currently hold is fine — it's
    only a write-time problem when the bar is feeding NAV."""
    today = _dt.date(2026, 6, 14)
    stale_date = today - _dt.timedelta(days=REFUSE_WRITE_STALE_DAYS + 5)
    bars = {
        "AAPL": (today, 210.0, 215.0),
        "OLD":  (stale_date, 1.0, 1.0),
    }
    r = validate_bars(bars, {"AAPL"}, today)
    assert r.ok


# ── closed_lots_hit_rate (FIFO closed-lot tracking) ─────────────────────


def _t(ticker: str, side: str, qty: float, price: float) -> TradeRecord:
    return TradeRecord(ticker=ticker, side=side, qty=qty, price=price)


def test_hit_rate_none_when_no_sells():
    """Bootstrap-only book has no closed lots → ratio is None
    (UI renders '—', not 0%)."""
    trades = [_t("AAPL", "buy", 50.0, 200.0), _t("JPM", "buy", 30.0, 250.0)]
    wins, total, ratio = closed_lots_hit_rate(trades)
    assert (wins, total) == (0, 0)
    assert ratio is None


def test_hit_rate_single_winning_close():
    trades = [
        _t("AAPL", "buy",  50.0, 200.0),
        _t("AAPL", "sell", 50.0, 220.0),  # +10% on the single lot
    ]
    wins, total, ratio = closed_lots_hit_rate(trades)
    assert (wins, total) == (1, 1)
    assert ratio == 1.0


def test_hit_rate_single_losing_close():
    trades = [
        _t("AAPL", "buy",  50.0, 200.0),
        _t("AAPL", "sell", 50.0, 180.0),  # -10%
    ]
    wins, total, ratio = closed_lots_hit_rate(trades)
    assert (wins, total) == (0, 1)
    assert ratio == 0.0


def test_hit_rate_fifo_partial_sell_consumes_oldest_lot_first():
    """Two buys at different prices, one sell that only consumes the
    first lot — the closed-lot result depends on the OLDEST buy
    price."""
    trades = [
        _t("AAPL", "buy",  50.0, 200.0),  # oldest lot
        _t("AAPL", "buy",  30.0, 250.0),  # newer lot, untouched by sell
        _t("AAPL", "sell", 30.0, 220.0),  # vs oldest @200 → win
    ]
    wins, total, ratio = closed_lots_hit_rate(trades)
    assert (wins, total) == (1, 1)
    assert ratio == 1.0


def test_hit_rate_sell_spans_multiple_lots():
    """One sell larger than the first lot creates two closed lots — one
    per consumed lot, judged independently."""
    trades = [
        _t("AAPL", "buy",  10.0, 100.0),  # cheap lot
        _t("AAPL", "buy",  10.0, 300.0),  # expensive lot
        _t("AAPL", "sell", 15.0, 200.0),  # vs 100 win, vs 300 loss
    ]
    wins, total, ratio = closed_lots_hit_rate(trades)
    assert (wins, total) == (1, 2)
    assert ratio == 0.5


def test_hit_rate_independent_per_ticker():
    trades = [
        _t("AAPL", "buy",  10.0, 100.0),
        _t("AAPL", "sell", 10.0, 150.0),   # win
        _t("JPM",  "buy",   5.0, 250.0),
        _t("JPM",  "sell",  5.0, 200.0),   # loss
    ]
    wins, total, ratio = closed_lots_hit_rate(trades)
    assert (wins, total) == (1, 2)
    assert ratio == 0.5


def test_hit_rate_sell_clipped_when_exceeds_open_lots():
    """A sell larger than total open qty is a paper-engine bug, but the
    function clips silently rather than raising — surfaces as no
    further closed lots until more buys land."""
    trades = [
        _t("AAPL", "buy",  10.0, 100.0),
        _t("AAPL", "sell", 50.0, 150.0),  # only 10 share-units close
        _t("AAPL", "buy",  20.0, 200.0),
        _t("AAPL", "sell", 20.0, 250.0),
    ]
    wins, total, ratio = closed_lots_hit_rate(trades)
    # 10 closed at +50% (win) + 20 closed at +25% (win) = 2 winning lots
    assert (wins, total) == (2, 2)
    assert ratio == 1.0


def test_hit_rate_ignores_unknown_side_strings():
    """Defensive: an unexpected side string is logged-only elsewhere
    and ignored here, not crashing the perf write."""
    trades = [
        _t("AAPL", "buy",  10.0, 100.0),
        _t("AAPL", "dividend", 1.0, 1.0),  # noise
        _t("AAPL", "sell", 10.0, 110.0),
    ]
    wins, total, ratio = closed_lots_hit_rate(trades)
    assert (wins, total) == (1, 1)
    assert ratio == 1.0

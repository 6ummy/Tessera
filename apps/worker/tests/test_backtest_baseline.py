"""Backtest-baseline pure-core tests (no DB/LLM).

Pins the three deterministic pieces: the weekly replay schedule, the
hold-and-rebalance simulation (built on paper_engine's NAV-conserving
fills), the full-window Sharpe/MDD metrics, and the per-persona
shortlist override (PR11 — Cathie's crypto sleeve preserved).
"""

from __future__ import annotations

from datetime import date

import pytest

from tessera_worker.jobs.backtest_baseline import (
    DayBar,
    _tickers_for,
    baseline_metrics,
    simulate_track,
    weekly_replay_dates,
)
from tessera_worker.jobs.persona_batch import PERSONA_SHORTLISTS

D = date


def test_weekly_replay_dates_spacing_and_weekday():
    dates = weekly_replay_dates(D(2026, 6, 12), 4)  # Fri
    assert len(dates) == 4
    assert dates == sorted(dates)          # oldest first
    assert dates[-1] == D(2026, 6, 12)
    for i in range(1, len(dates)):
        assert (dates[i] - dates[i - 1]).days == 7
    assert all(d.weekday() < 5 for d in dates)


def test_weekly_replay_backs_off_weekend():
    # Sunday → anchor on the preceding Friday
    assert weekly_replay_dates(D(2026, 6, 14), 1)[0] == D(2026, 6, 12)


def test_simulate_frozen_book_curve():
    """One book on day 1, held: equity curve tracks the close moves."""
    days = [D(2026, 6, 1), D(2026, 6, 2), D(2026, 6, 3)]
    bars = {
        "AAPL": {
            days[0]: DayBar(open=100.0, close=100.0),
            days[1]: DayBar(open=101.0, close=110.0),
            days[2]: DayBar(open=110.0, close=99.0),
        },
    }
    books = {days[0]: {"AAPL": 1.0}}  # all-in AAPL at day-1 open (100)
    curve = simulate_track(books, bars, days)
    assert curve[0][1] == pytest.approx(100_000.0)         # bought at 100, close 100
    assert curve[1][1] == pytest.approx(110_000.0)         # close 110
    assert curve[2][1] == pytest.approx(99_000.0)          # close 99


def test_simulate_rebalances_at_new_book():
    days = [D(2026, 6, 1), D(2026, 6, 2)]
    bars = {
        "AAPL": {days[0]: DayBar(100.0, 100.0), days[1]: DayBar(100.0, 100.0)},
        "JPM":  {days[0]: DayBar(50.0, 50.0),   days[1]: DayBar(50.0, 50.0)},
    }
    books = {
        days[0]: {"AAPL": 1.0},               # day1: all AAPL
        days[1]: {"AAPL": 0.5, "JPM": 0.5},   # day2: split
    }
    curve = simulate_track(books, bars, days)
    # flat prices → NAV conserved at 100k both days
    assert curve[-1][1] == pytest.approx(100_000.0)


def test_baseline_metrics_sharpe_and_mdd():
    curve = [
        (D(2026, 6, 1), 100_000.0),
        (D(2026, 6, 2), 110_000.0),
        (D(2026, 6, 3), 121_000.0),
        (D(2026, 6, 4), 108_900.0),  # -10% from peak
        (D(2026, 6, 5), 119_790.0),
        (D(2026, 6, 8), 125_780.0),
    ]
    m = baseline_metrics(curve)
    assert m.days == 6
    assert m.total_return == pytest.approx(0.2578, abs=1e-3)
    assert m.max_drawdown == pytest.approx(0.10, abs=1e-3)  # 121k → 108.9k
    assert m.annualized_sharpe is not None


def test_baseline_metrics_degenerate():
    assert baseline_metrics([]).annualized_sharpe is None
    assert baseline_metrics([(D(2026, 6, 1), 100.0)]).total_return == 0.0


# ─── PR11: per-persona shortlist truncation override ────────────────────


def test_tickers_for_cathie_always_returns_full_shortlist():
    """Cathie's 14-name shortlist (10 equity + 4 crypto) must be passed
    in full regardless of n, because the construction call's Tech 70%
    sector cap is mathematically unsatisfiable from the equity-only
    truncated slice. 2026-06-14 baseline failed 6/9 Cathie cells
    exactly this way."""
    full = PERSONA_SHORTLISTS["cathie"]
    assert len(full) == 14
    # n=10 (the value used in the 2026-06-14 baseline) — must NOT
    # truncate cathie:
    assert _tickers_for("cathie", 10) == full
    # n=5 — same:
    assert _tickers_for("cathie", 5) == full
    # n=100 (over the shortlist length) — also returns the full list:
    assert _tickers_for("cathie", 100) == full
    # And the crypto sleeve is still in there:
    assert any(t.endswith("/USD") for t in _tickers_for("cathie", 10))


def test_tickers_for_other_personas_still_truncate():
    """Warren / Peter shortlists are sector-balanced 10-name lists; the
    truncation for them was never the source of the constraint
    infeasibility, so we keep the old behavior."""
    assert _tickers_for("warren", 5) == PERSONA_SHORTLISTS["warren"][:5]
    assert _tickers_for("peter", 7) == PERSONA_SHORTLISTS["peter"][:7]
    # n past the list length: returns whatever's there (no padding)
    assert _tickers_for("warren", 100) == PERSONA_SHORTLISTS["warren"]

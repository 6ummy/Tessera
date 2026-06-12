"""Frozen-book backfill math tests (pure core, no DB).

The two invariants that make the hypothetical track trustworthy:
  1. valuation = cash + Σ(frozen_qty × forward-filled close), never a
     partially-priced book (leading days skip until every ticker prices);
  2. performance is measured against the segment's own first day, and
     the seam into the real track is continuous by construction because
     the frozen quantities ARE the first real snapshot's quantities.
"""

from __future__ import annotations

from datetime import date

import pytest

from tessera_worker.jobs.backfill_paper_history import (
    build_performance_rows,
    build_value_series,
)

D = date  # brevity


def test_values_frozen_book_at_daily_closes():
    calendar = [D(2025, 6, 2), D(2025, 6, 3)]
    closes = {
        "AAPL": {D(2025, 6, 2): 100.0, D(2025, 6, 3): 110.0},
        "JPM": {D(2025, 6, 2): 200.0, D(2025, 6, 3): 190.0},
    }
    series = build_value_series(calendar, closes, {"AAPL": 10.0, "JPM": 5.0}, 500.0)

    assert [dv.day for dv in series] == calendar
    assert series[0].total_value == pytest.approx(500 + 1000 + 1000)
    assert series[1].total_value == pytest.approx(500 + 1100 + 950)


def test_forward_fill_carries_last_close():
    """Crypto-style gaps: JPM has no bar on the 3rd — its last close
    carries; the day still produces a fully-priced row."""
    calendar = [D(2025, 6, 2), D(2025, 6, 3)]
    closes = {
        "AAPL": {D(2025, 6, 2): 100.0, D(2025, 6, 3): 110.0},
        "JPM": {D(2025, 6, 2): 200.0},
    }
    series = build_value_series(calendar, closes, {"AAPL": 1.0, "JPM": 1.0}, 0.0)
    assert series[1].total_value == pytest.approx(110.0 + 200.0)
    assert series[1].position_values["JPM"][0] == 200.0  # ffilled close


def test_grace_window_seeds_forward_fill():
    """A close BEFORE the calendar start (grace window) seeds the fill —
    the first calendar day prices even without a same-day bar."""
    calendar = [D(2025, 6, 2)]
    closes = {"AAPL": {D(2025, 5, 30): 95.0}}
    series = build_value_series(calendar, closes, {"AAPL": 2.0}, 10.0)
    assert len(series) == 1
    assert series[0].total_value == pytest.approx(10.0 + 190.0)


def test_leading_days_skipped_until_fully_priced():
    """A ticker that hasn't traded yet (post-start listing) must not
    produce understated rows — leading days are dropped, not zero-filled."""
    calendar = [D(2025, 6, 2), D(2025, 6, 3), D(2025, 6, 4)]
    closes = {
        "AAPL": {D(2025, 6, 2): 100.0, D(2025, 6, 3): 100.0, D(2025, 6, 4): 100.0},
        "NEWCO": {D(2025, 6, 3): 50.0, D(2025, 6, 4): 55.0},
    }
    series = build_value_series(calendar, closes, {"AAPL": 1.0, "NEWCO": 1.0}, 0.0)
    assert [dv.day for dv in series] == [D(2025, 6, 3), D(2025, 6, 4)]


def test_all_cash_book_is_flat():
    calendar = [D(2025, 6, 2), D(2025, 6, 3)]
    series = build_value_series(calendar, {}, {}, 100_000.0)
    assert [dv.total_value for dv in series] == [100_000.0, 100_000.0]


# ── performance rows ─────────────────────────────────────────────────────

def test_performance_baseline_is_first_hypothetical_day():
    calendar = [D(2025, 6, 2), D(2025, 6, 3), D(2025, 6, 4)]
    closes = {"A": {D(2025, 6, 2): 100.0, D(2025, 6, 3): 110.0,
                    D(2025, 6, 4): 99.0}}
    series = build_value_series(calendar, closes, {"A": 1.0}, 0.0)
    perf = build_performance_rows(series)

    assert perf[0].pnl_day == pytest.approx(0.0)
    assert perf[0].return_cum == pytest.approx(0.0)
    assert perf[1].return_day == pytest.approx(0.10)
    assert perf[1].return_cum == pytest.approx(0.10)
    assert perf[2].return_cum == pytest.approx(-0.01)
    # day-3 drawdown: peak 110 → 99 = 10%
    assert perf[2].mdd == pytest.approx(0.10)


def test_performance_empty_series():
    assert build_performance_rows([]) == []

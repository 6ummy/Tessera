"""Attribution math tests (risk/attribution.py pure core).

The invariant worth pinning: with flows priced at the close (the v1
convention), the sum of per-ticker contributions equals the period's
total return whenever cash is constant — and stays a close approximation
through rebalances.
"""

from __future__ import annotations

from datetime import date

import pytest

from tessera_worker.risk.attribution import Snapshot, compute_attribution

D = date


def test_frozen_book_contributions_sum_to_period_return():
    """Constant qty (the backfill case): contributions must reconstruct
    the period return exactly."""
    snaps = [
        Snapshot(D(2026, 6, 1), {"AAPL": (10.0, 100.0), "JPM": (4.0, 250.0)}, 3000.0),
        Snapshot(D(2026, 6, 2), {"AAPL": (10.0, 110.0), "JPM": (4.0, 240.0)}, 3060.0),
        Snapshot(D(2026, 6, 3), {"AAPL": (10.0, 105.0), "JPM": (4.0, 260.0)}, 3090.0),
    ]
    rows = compute_attribution(snaps)
    by_ticker = {a.ticker: a for a in rows}

    assert by_ticker["AAPL"].pnl == pytest.approx(10 * (105 - 100))
    assert by_ticker["JPM"].pnl == pytest.approx(4 * (260 - 250))
    total_contribution = sum(a.contribution for a in rows)
    assert total_contribution == pytest.approx(3090.0 / 3000.0 - 1.0, abs=1e-6)


def test_rebalance_day_attributes_prior_holding_only():
    """qty change on day 2: day-2 move is attributed at day-1 qty —
    the traded delta's same-day move is deliberately unattributed."""
    snaps = [
        Snapshot(D(2026, 6, 1), {"AAPL": (10.0, 100.0)}, 1000.0),
        Snapshot(D(2026, 6, 2), {"AAPL": (20.0, 110.0)}, 2200.0),  # bought 10 more
        Snapshot(D(2026, 6, 3), {"AAPL": (20.0, 115.0)}, 2300.0),
    ]
    rows = compute_attribution(snaps)
    # day2: 10 × (110−100) = 100 ; day3: 20 × (115−110) = 100
    assert rows[0].pnl == pytest.approx(200.0)


def test_closed_position_keeps_realized_move():
    snaps = [
        Snapshot(D(2026, 6, 1), {"AAPL": (10.0, 100.0)}, 1000.0),
        Snapshot(D(2026, 6, 2), {"AAPL": (10.0, 90.0)}, 900.0),
        Snapshot(D(2026, 6, 3), {}, 900.0),  # closed at the 6/2 close
    ]
    rows = compute_attribution(snaps)
    assert rows[0].ticker == "AAPL"
    assert rows[0].pnl == pytest.approx(-100.0)


def test_attribution_sorted_by_magnitude_and_needs_two_snapshots():
    assert compute_attribution([]) == []
    assert compute_attribution(
        [Snapshot(D(2026, 6, 1), {}, 1.0)]) == []
    snaps = [
        Snapshot(D(2026, 6, 1), {"A": (1.0, 100.0), "B": (1.0, 100.0)}, 200.0),
        Snapshot(D(2026, 6, 2), {"A": (1.0, 101.0), "B": (1.0, 80.0)}, 181.0),
    ]
    rows = compute_attribution(snaps)
    assert [a.ticker for a in rows] == ["B", "A"]  # |−20| > |+1|

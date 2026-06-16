"""Mirror-engine projection tests — the pure weight-projection arithmetic
that keeps a follower's book in sync with the persona they follow.

No DB: project_follower_book is a pure function, so the invariants (return
mirrors the persona since follow-date; weights preserved; NAV conserved)
pin without a session.
"""

from __future__ import annotations

import pytest

from tessera_worker.risk.mirror import project_follower_book


def test_follow_today_mirrors_weights_one_to_one():
    # Followed today (nav_at_start == nav_today), $100K. Persona book:
    # 60% AAPL, 40% cash → follower holds $60K AAPL, $40K cash.
    pos, cash, nav = project_follower_book(
        persona_positions={"AAPL": 600.0},   # 600 * 100 = 60,000
        persona_cash=40_000.0,
        nav_today=100_000.0,
        nav_at_start=100_000.0,
        starting_capital=100_000.0,
        closes={"AAPL": 100.0},
    )
    assert nav == pytest.approx(100_000.0)
    assert cash == pytest.approx(40_000.0)
    assert pos["AAPL"]["value"] == pytest.approx(60_000.0)
    assert pos["AAPL"]["qty"] == pytest.approx(600.0)


def test_return_since_follow_equals_persona_return():
    # Followed when the persona NAV was 90K; it's 100K now → the follower
    # is up the same +11.11%, regardless of their own capital.
    _pos, cash, nav = project_follower_book(
        persona_positions={"NVDA": 500.0},   # 500 * 100 = 50,000 (50%)
        persona_cash=50_000.0,
        nav_today=100_000.0,
        nav_at_start=90_000.0,
        starting_capital=100_000.0,
        closes={"NVDA": 100.0},
    )
    assert nav == pytest.approx(100_000.0 * (100_000.0 / 90_000.0))
    # Weights preserved: still 50/50.
    assert cash == pytest.approx(nav * 0.5)


def test_fractional_capital_scales():
    # A $10K follower of the same book holds 1/10th the dollar values.
    pos, cash, nav = project_follower_book(
        persona_positions={"MSFT": 200.0},   # 200 * 200 = 40,000 (40%)
        persona_cash=60_000.0,
        nav_today=100_000.0,
        nav_at_start=100_000.0,
        starting_capital=10_000.0,
        closes={"MSFT": 200.0},
    )
    assert nav == pytest.approx(10_000.0)
    assert pos["MSFT"]["value"] == pytest.approx(4_000.0)
    assert cash == pytest.approx(6_000.0)


def test_nav_conserved_across_positions_and_cash():
    pos, cash, nav = project_follower_book(
        persona_positions={"AAPL": 300.0, "JPM": 200.0},  # 30k + 20k
        persona_cash=50_000.0,
        nav_today=100_000.0,
        nav_at_start=100_000.0,
        starting_capital=100_000.0,
        closes={"AAPL": 100.0, "JPM": 100.0},
    )
    total = cash + sum(p["value"] for p in pos.values())
    assert total == pytest.approx(nav, abs=0.01)


def test_missing_close_drops_to_cash_gap():
    # A held ticker with no usable price is dropped from positions; the
    # caller's NAV still reflects the full projection (the gap shows up as
    # positions summing below nav, not a silent overstate).
    pos, cash, nav = project_follower_book(
        persona_positions={"AAPL": 500.0, "ZZZZ": 100.0},
        persona_cash=0.0,
        nav_today=100_000.0,
        nav_at_start=100_000.0,
        starting_capital=100_000.0,
        closes={"AAPL": 100.0},  # ZZZZ price missing
    )
    assert "ZZZZ" not in pos
    assert "AAPL" in pos
    assert cash == pytest.approx(0.0)
    assert nav == pytest.approx(100_000.0)

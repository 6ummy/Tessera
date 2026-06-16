"""normalize_book tests — the deterministic enforcer of weights+cash=1.0.

This function is the reason the construction LLM's arithmetic mistakes
never reach the DB, so its invariant — the returned book ALWAYS sums to
1.0 within rounding — is pinned across every code path: scale-down,
gap-to-cash, cash clamping, single-name clipping, and the
impossible-envelope fallback.
"""

from __future__ import annotations

import pytest

from tessera_worker.agents.persona_constraints import (
    constraints_for,
    constraints_prompt_block,
)
from tessera_worker.agents.portfolio_construction import (
    normalize_book,
    position_count_violation,
    research_to_payload_dict,
)


def _total(weights: dict[str, float], cash: float) -> float:
    return sum(weights.values()) + cash


def _assert_book_invariants(
    weights: dict[str, float], cash: float, *, max_single_name: float,
) -> None:
    assert _total(weights, cash) == pytest.approx(1.0, abs=0.005)
    for t, w in weights.items():
        assert w <= max_single_name + 1e-9, f"{t} over cap"
        assert w >= 0.005, f"{t} should have been dropped as dust"


# ── happy path ───────────────────────────────────────────────────────────

def test_coherent_book_passes_through():
    weights, cash = normalize_book(
        {"AAPL": 0.15, "MSFT": 0.15, "COST": 0.10}, 0.60,
        max_single_name=0.18, cash_min=0.0, cash_max=1.0,
    )
    assert weights == {"AAPL": 0.15, "MSFT": 0.15, "COST": 0.10}
    assert cash == pytest.approx(0.60)


# ── the LLM miscounts ────────────────────────────────────────────────────

def test_over_allocation_scales_down():
    """Sum 1.30 + cash 0.10 — positions scale to fit, never reject."""
    weights, cash = normalize_book(
        {"A": 0.50, "B": 0.50, "C": 0.30}, 0.10,
        max_single_name=0.60, cash_min=0.05, cash_max=0.50,
    )
    _assert_book_invariants(weights, cash, max_single_name=0.60)
    # relative order preserved: A ≈ B (1pp rounding asymmetry allowed) > C
    assert weights["A"] == pytest.approx(weights["B"], abs=0.011)
    assert min(weights["A"], weights["B"]) > weights["C"]


def test_under_allocation_gap_goes_to_cash():
    """0.30 positions + 0.10 cash = 0.40 — the missing 0.60 is cash."""
    weights, cash = normalize_book(
        {"A": 0.20, "B": 0.10}, 0.10,
        max_single_name=0.25, cash_min=0.0, cash_max=1.0,
    )
    _assert_book_invariants(weights, cash, max_single_name=0.25)
    assert cash == pytest.approx(0.70)


def test_cash_above_max_scales_positions_up():
    """A book that already sums to 1.0 but parks 70% in cash against a
    10% cash_max (Cathie's mandate) must be rescaled — pre-2026-06-12 the
    clamp only ran when the SUM was wrong, so this sailed through.
    Envelope is feasible here (2 names × 0.60 cap + 0.10 cash ≥ 1.0)."""
    weights, cash = normalize_book(
        {"A": 0.20, "B": 0.10}, 0.70,
        max_single_name=0.60, cash_min=0.0, cash_max=0.10,
    )
    _assert_book_invariants(weights, cash, max_single_name=0.60)
    assert cash == pytest.approx(0.10, abs=0.011)
    assert weights["A"] == pytest.approx(2 * weights["B"], abs=0.02)


# ── single-name cap ──────────────────────────────────────────────────────

def test_single_name_cap_clips_and_redistributes():
    weights, cash = normalize_book(
        {"A": 0.40, "B": 0.10}, 0.50,
        max_single_name=0.18, cash_min=0.0, cash_max=1.0,
    )
    _assert_book_invariants(weights, cash, max_single_name=0.18)
    assert weights["A"] == pytest.approx(0.18)  # clipped to cap


# ── degenerate inputs ────────────────────────────────────────────────────

def test_empty_book_clamps_cash_to_range():
    weights, cash = normalize_book(
        {}, 0.30, max_single_name=0.18, cash_min=0.05, cash_max=0.25,
    )
    assert weights == {}
    assert cash == pytest.approx(0.25)


def test_negative_weights_are_floored():
    weights, cash = normalize_book(
        {"A": -0.10, "B": 0.20}, 0.80,
        max_single_name=0.25, cash_min=0.0, cash_max=1.0,
    )
    _assert_book_invariants(weights, cash, max_single_name=0.25)
    assert "A" not in weights  # floored to 0 → dropped as dust


def test_impossible_envelope_falls_back_to_cash():
    """Peter's pre-2026-06-10 trap: caps × shortlist can't reach 1.0
    (3 names × 0.10 cap = 0.30 max + cash_max 0.10 = 0.40 ceiling).
    The sum=1.0 invariant must win — cash absorbs beyond cash_max."""
    weights, cash = normalize_book(
        {"A": 0.30, "B": 0.30, "C": 0.30}, 0.10,
        max_single_name=0.10, cash_min=0.0, cash_max=0.10,
    )
    assert _total(weights, cash) == pytest.approx(1.0, abs=0.005)
    for w in weights.values():
        assert w <= 0.10 + 1e-9
    assert cash > 0.10  # deliberately beyond cash_max — logged at call site


def test_dust_positions_dropped():
    weights, _cash = normalize_book(
        {"A": 0.002, "B": 0.20}, 0.798,
        max_single_name=0.25, cash_min=0.0, cash_max=1.0,
    )
    assert "A" not in weights


# ── position_count_violation (hard count band, CS-11) ────────────────────

def test_position_count_within_band_passes():
    c = constraints_for("cathie")  # band is 10–12 since 2026-06-15
    assert position_count_violation(10, c) is None
    assert position_count_violation(12, c) is None


def test_position_count_below_floor_flagged():
    c = constraints_for("cathie")
    msg = position_count_violation(9, c)
    assert msg is not None and "≥10" in msg


def test_position_count_above_ceiling_flagged():
    c = constraints_for("cathie")
    msg = position_count_violation(13, c)
    assert msg is not None and "≤12" in msg


def test_cathie_max_positions_capped_at_12():
    # The product decision (2026-06-15): focused book, not a 20-name spray.
    assert constraints_for("cathie").target_position_count_max == 12


def test_cathie_has_no_sector_cap():
    # max_sector 1.0 = no operational cap; concentration is her mandate.
    assert constraints_for("cathie").max_sector >= 1.0
    block = constraints_prompt_block("cathie")
    assert "no cap" in block.lower()
    assert "Sector cap:" not in block  # the capped-persona phrasing is gone


def test_capped_persona_still_prints_sector_cap():
    block = constraints_prompt_block("warren")
    assert "Sector cap: 50% of NAV" in block


# ── research_to_payload_dict ─────────────────────────────────────────────

def test_research_payload_from_pydantic_and_dict():
    from tessera_shared.schemas import TickerResearch

    model = TickerResearch(
        ticker="AAPL", conviction=0.7,
        thesis_md="a thesis with enough characters to validate",
        bull_case="upside case here", bear_case="downside case here",
    )
    from_model = research_to_payload_dict(model)
    from_dict = research_to_payload_dict({"ticker": "AAPL", "conviction": 0.7})

    assert from_model["ticker"] == from_dict["ticker"] == "AAPL"
    assert from_model["conviction"] == pytest.approx(0.7)
    # missing conviction defaults to neutral 0.5, not 0 (a zero would
    # silently watchlist the name in construction)
    assert research_to_payload_dict({"ticker": "X"})["conviction"] == 0.5

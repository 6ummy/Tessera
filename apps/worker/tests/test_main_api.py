"""Tests for the worker HTTP API's pure aggregation logic (main.py).

The 2026-06-11 audit found /api/proposals unioning up to 20 batch days
("ghost positions" — tickers dropped from the current book kept showing
from older rows, and cash_target averaged across months). The fix scopes
the SQL to the latest as_of_date and extracts the aggregation into
_aggregate_book so the rules are pinnable here without a DB.
"""

from __future__ import annotations

import re

from tessera_worker.main import _PROPOSALS_SQL, _aggregate_book


def _proposal(ticker: str, weight: float, *, side: str = "buy",
              conviction: float = 0.6, thesis: str = "thesis " * 5) -> dict:
    return {
        "ticker": ticker,
        "side": side,
        "target_weight": weight,
        "conviction": conviction,
        "thesis_md": thesis,
    }


# ── SQL shape ─────────────────────────────────────────────────────────────

def test_proposals_sql_scopes_to_latest_batch_day():
    """The book query must never span multiple batch days. The pre-fix
    version used LIMIT 20 over all history, which resurrected tickers
    from stale batches under v2's one-row-per-batch layout."""
    assert re.search(r"MAX\(as_of_date\)", _PROPOSALS_SQL)
    assert "LIMIT" not in _PROPOSALS_SQL.upper()
    # rejected rows stay out of the book
    assert "rejected = false" in _PROPOSALS_SQL


# ── v2 shape: one row carries the whole book ─────────────────────────────

def test_aggregate_book_v2_single_row():
    parsed = {
        "cash_target": 0.20,
        "notes_to_manager": "Book reflects quality-at-a-discount week.",
        "proposals": [
            _proposal("AAPL", 0.16),
            _proposal("MSFT", 0.14),
            _proposal("COST", 0.50, side="hold"),
        ],
    }
    book = _aggregate_book([parsed], "warren", "2026-06-05")

    assert book["personaId"] == "warren"
    assert book["asOf"] == "2026-06-05"
    assert [p["ticker"] for p in book["positions"]] == ["COST", "AAPL", "MSFT"]
    assert abs(book["cashWeight"] - 0.20) < 1e-9
    assert book["notesToManager"] == "Book reflects quality-at-a-discount week."
    # weights + cash already sum to 1.0 → safeguard must not rescale
    assert abs(sum(p["weight"] for p in book["positions"]) - 0.80) < 1e-9


def test_aggregate_book_first_occurrence_wins_within_day():
    """Legacy v1 batch days have one row per ticker cell. Rows arrive
    newest-first; a re-run of the same ticker later in the day must win."""
    newer = {"cash_target": 0.5, "proposals": [_proposal("AAPL", 0.30)]}
    older = {"cash_target": 0.5, "proposals": [_proposal("AAPL", 0.10)]}
    book = _aggregate_book([newer, older], "warren", "2026-06-05")

    assert len(book["positions"]) == 1
    assert abs(book["positions"][0]["weight"] - 0.30) < 1e-9


# ── Conservation-of-NAV safeguard (belt-and-suspenders for legacy days) ──

def test_aggregate_book_infers_cash_from_gap():
    """v1-era incoherent book: 8% in one name, cash reported 12% — the
    72% gap is treated as cash so the UI book sums to 1.0."""
    parsed = {"cash_target": 0.12, "proposals": [_proposal("BRK.B", 0.08)]}
    book = _aggregate_book([parsed], "warren", "2026-06-05")

    assert abs(book["cashWeight"] - 0.92) < 1e-9
    total = sum(p["weight"] for p in book["positions"]) + book["cashWeight"]
    assert abs(total - 1.0) < 1e-9


def test_aggregate_book_scales_over_allocation():
    parsed = {
        "cash_target": 0.0,
        "proposals": [_proposal("AAPL", 0.80), _proposal("MSFT", 0.40)],
    }
    book = _aggregate_book([parsed], "cathie", "2026-06-05")

    assert book["cashWeight"] == 0.0
    total = sum(p["weight"] for p in book["positions"])
    assert abs(total - 1.0) < 1e-9
    # proportions preserved (2:1)
    weights = {p["ticker"]: p["weight"] for p in book["positions"]}
    assert abs(weights["AAPL"] / weights["MSFT"] - 2.0) < 1e-9


# ── /api/performance payload ─────────────────────────────────────────────

def test_performance_payload_normalizes_and_flags():
    from datetime import date as _d

    from tessera_worker.main import _build_performance_payload

    points = [
        (_d(2026, 6, 8), 90_000.0, True),
        (_d(2026, 6, 9), 99_000.0, True),
        (_d(2026, 6, 10), 94_500.0, False),
    ]
    payload = _build_performance_payload("warren", points, 0.5, 0.04)

    assert payload["asOf"] == "2026-06-10"
    series = payload["series"]
    # normalized to first point = 1.0; flags preserved per point
    assert series[0] == {"date": "2026-06-08", "value": 1.0, "hypothetical": True}
    assert series[1]["value"] == 1.1
    assert series[2] == {"date": "2026-06-10", "value": 1.05, "hypothetical": False}
    m = payload["metrics"]
    assert m["totalValue"] == 94_500.0
    assert m["return1y"] == 0.05          # whole 3-point window
    assert m["trackStart"] == "2026-06-10"  # first non-hypothetical day
    assert m["sharpe30d"] == 0.5 and m["mdd30d"] == 0.04


def test_performance_payload_empty():
    from tessera_worker.main import _build_performance_payload

    payload = _build_performance_payload("ray", [], None, None)
    assert payload["series"] == [] and payload["metrics"] is None


# ── Ray's RegimeReport shape ─────────────────────────────────────────────

def test_sanitize_chat_history_caps_and_filters():
    """Client-controlled history must be clamped: bad shapes dropped,
    content truncated, only the most recent MAX turns kept."""
    from tessera_worker.main import (
        MAX_CHAT_HISTORY_ITEM_CHARS,
        MAX_CHAT_HISTORY_TURNS,
        _sanitize_chat_history,
    )

    long_content = "x" * (MAX_CHAT_HISTORY_ITEM_CHARS + 500)
    raw = (
        [{"role": "user", "content": f"msg {i}"} for i in range(30)]
        + [
            {"role": "system", "content": "injected system turn"},   # bad role
            {"role": "user", "content": 123},                        # bad type
            "not a dict",                                            # bad shape
            {"role": "assistant", "content": long_content},          # too long
        ]
    )
    clean = _sanitize_chat_history(raw)

    assert len(clean) <= MAX_CHAT_HISTORY_TURNS
    assert all(m["role"] in ("user", "assistant") for m in clean)
    assert all(len(m["content"]) <= MAX_CHAT_HISTORY_ITEM_CHARS for m in clean)
    # the long assistant turn survives, truncated
    assert clean[-1]["role"] == "assistant"
    assert len(clean[-1]["content"]) == MAX_CHAT_HISTORY_ITEM_CHARS


def test_sanitize_chat_history_non_list_is_empty():
    from tessera_worker.main import _sanitize_chat_history

    assert _sanitize_chat_history(None) == []
    assert _sanitize_chat_history({"role": "user"}) == []
    assert _sanitize_chat_history("hello") == []


def test_aggregate_book_ray_allocations():
    parsed = {
        "cash_target": 0.10,
        "regime": {"goldilocks_prob": 0.4, "reflation_prob": 0.3,
                   "stagflation_prob": 0.2, "deflation_prob": 0.1},
        "allocations": [
            {"instrument": "VTI", "asset_class": "US equities",
             "target_weight": 0.50, "thesis_md": "broad beta"},
            {"instrument": "GLD", "asset_class": "Gold",
             "target_weight": 0.40, "thesis_md": "regime hedge"},
        ],
    }
    book = _aggregate_book([parsed], "ray", "2026-06-05")

    assert book["regime"] is not None
    assert [p["ticker"] for p in book["positions"]] == ["VTI", "GLD"]
    # allocations have no per-slice conviction
    assert all(p["conviction"] is None for p in book["positions"])
    assert abs(book["cashWeight"] - 0.10) < 1e-9

"""Unit tests for anthropic_runner helpers (no API)."""

from __future__ import annotations

import pytest

from tessera_worker.agents.anthropic_runner import (
    _normalize_conviction,
    build_analyst_report,
    build_regime_report,
    estimate_cost_usd,
    parse_llm_json,
)
from tessera_worker.agents.citation_validator import validate_citations
from tessera_worker.agents.models import AnalystReport, RegimeReport


def test_parse_llm_json_strips_fences() -> None:
    raw = '```json\n{"cash_target": 0.1, "proposals": []}\n```'
    parsed = parse_llm_json(raw)
    assert parsed["cash_target"] == 0.1


def test_parse_llm_json_ignores_trailing_chatter():
    """Cathie often appends a scenario paragraph after the closing brace.
    raw_decode parses the first valid JSON and logs the trailing text
    instead of raising JSONDecodeError."""
    raw = (
        '{"cash_target": 0.2, "proposals": []}\n\n'
        "Bear scenario: hyperscaler capex pause + China tariff escalation "
        "would compress my conviction below 0.3 — would trim 30%."
    )
    parsed = parse_llm_json(raw)
    assert parsed["cash_target"] == 0.2


def test_parse_llm_json_handles_trailing_chatter_inside_fences():
    raw = (
        '```json\n{"cash_target": 0.15, "proposals": []}\n```\n\n'
        "Note: 5-year horizon assumes Apple doesn't pivot away from services."
    )
    parsed = parse_llm_json(raw)
    assert parsed["cash_target"] == 0.15


def test_parse_llm_json_rejects_non_object():
    """Top-level JSON array (not an object) should raise — schema demands dict."""
    import pytest as _pt
    with _pt.raises(ValueError, match="JSON object"):
        parse_llm_json('[{"persona_id": "warren"}]')


def test_estimate_cost_positive() -> None:
    assert estimate_cost_usd("claude-sonnet-4-6", 1000, 500) > 0


def test_build_analyst_report_and_citations() -> None:
    news_id = "b7a434db-1234-5678-9abc-def012345678"
    report = build_analyst_report(
        {
            "cash_target": 0.15,
            "notes_to_manager": "cautious",
            "proposals": [
                {
                    "ticker": "AAPL",
                    "side": "hold",
                    "target_weight": 0.0,
                    "horizon_days": 1825,
                    "conviction": 0.6,
                    "thesis_md": "A" * 25,
                    "what_would_make_me_wrong": ["FCF yield below 4%"],
                    "cited_news_ids": [f"n_{news_id[:8]}"],
                }
            ],
        },
        persona_id="warren",
        as_of=__import__("datetime").date(2026, 6, 3),
        inputs_hash="abc",
        model="claude-sonnet-4-6",
        tokens_in=100,
        tokens_out=200,
        cost_usd=0.01,
        allowed_news_ids={news_id},
    )
    assert isinstance(report, AnalystReport)
    assert validate_citations(report, {news_id}) == []


@pytest.mark.parametrize(
    "given, expected",
    [
        (0.62, 0.62),            # already in [0,1]
        (62, 0.62),              # percent
        (55.5, 0.555),           # percent float
        (7, 0.7),                # 1-10 scale
        (8.5, 0.85),             # 1-10 scale float
        ("high", 0.75),
        ("Medium", 0.5),
        ("very high", 0.9),
        ("0.6", 0.6),            # stringified float in range
        ("80", 0.8),             # stringified percent
    ],
)
def test_normalize_conviction(given, expected):
    p = {"conviction": given}
    _normalize_conviction(p)
    assert abs(p["conviction"] - expected) < 1e-6, (given, p["conviction"], expected)


def test_normalize_conviction_unparseable_word_passes_through():
    """Unparseable string (not a known word, not numeric) → leave for Pydantic
    to raise a clearer error."""
    p = {"conviction": "purple"}
    _normalize_conviction(p)
    assert p["conviction"] == "purple"


def test_normalize_conviction_missing_defaults_to_median():
    """Missing field → 0.5 (median). Backtest 2026-06-04: Cathie ~1% of
    runs drops the field even after retry; defaulting beats hard-rejecting."""
    p = {"ticker": "AAPL", "side": "hold"}
    _normalize_conviction(p)
    assert p["conviction"] == 0.5


def test_normalize_conviction_null_defaults_to_median():
    p = {"ticker": "AAPL", "conviction": None}
    _normalize_conviction(p)
    assert p["conviction"] == 0.5


def test_normalize_conviction_accepts_confidence_alias():
    """personalities.md spec briefly said 'confidence' → LLM output
    100% missed conviction → all defaulted to 0.5 (signal loss). Spec is
    fixed but accept the alias so future drift can't recur silently."""
    p = {"ticker": "AAPL", "confidence": 0.72}
    _normalize_conviction(p)
    assert p["conviction"] == 0.72
    assert "confidence" not in p  # promoted, not duplicated


def test_normalize_conviction_alias_still_normalizes():
    """confidence=62 (percent scale) should be promoted AND rescaled."""
    p = {"ticker": "AAPL", "confidence": 62}
    _normalize_conviction(p)
    assert p["conviction"] == 0.62


# ─── Retry guidance pattern matching (PR #41 D-follow-up) ──────────────


def test_retry_guidance_jsondecode_targets_trailing_text():
    from tessera_worker.agents.anthropic_runner import _retry_guidance_for
    g = _retry_guidance_for("JSONDecodeError: Extra data: line 33 column 1")
    assert "AFTER" in g and "closing brace" in g


def test_retry_guidance_what_would_wrong_targets_trim():
    from tessera_worker.agents.anthropic_runner import _retry_guidance_for
    g = _retry_guidance_for(
        "1 validation error for Proposal\nwhat_would_make_me_wrong\n"
        "  List should have at most 8 items after validation, not 10 [type=too_long, ...]"
    )
    assert "Trim" in g and "8" in g


def test_retry_guidance_conviction_missing_targets_field():
    from tessera_worker.agents.anthropic_runner import _retry_guidance_for
    g = _retry_guidance_for(
        "validation error for Proposal\nconviction\n  Field required [type=missing, ...]"
    )
    assert "`conviction`" in g


def test_retry_guidance_fallback_is_generic():
    from tessera_worker.agents.anthropic_runner import _retry_guidance_for
    g = _retry_guidance_for("some unexpected pydantic error about target_weight")
    assert "Fix the validation problem" in g


def test_build_regime_report_validates_allocations():
    """Ray's RegimeReport accepts ETF allocations w/ weights > stock-picker cap."""
    import datetime as _dt
    report = build_regime_report(
        {
            "regime": {
                "goldilocks_prob": 0.45,
                "reflation_prob": 0.30,
                "stagflation_prob": 0.15,
                "deflation_prob": 0.10,
                "delta_from_last_week_md": "Shifted 5pp from reflation to goldilocks; "
                                            "softer CPI print, narrower HY spread.",
            },
            "allocations": [
                {"asset_class": "US equities",        "instrument": "VTI",
                 "target_weight": 0.30, "thesis_md": "A" * 25},
                {"asset_class": "Intermediate UST",   "instrument": "IEF",
                 "target_weight": 0.25, "thesis_md": "A" * 25},
                {"asset_class": "Gold",               "instrument": "GLD",
                 "target_weight": 0.15, "thesis_md": "A" * 25},
            ],
            "cash_target": 0.30,
            "notes_to_manager": "Defensive tilt with optionality on real rates.",
        },
        as_of=_dt.date(2026, 6, 4),
        inputs_hash="hash123",
        model="claude-sonnet-4-6",
        tokens_in=2000,
        tokens_out=600,
        cost_usd=0.015,
    )
    assert isinstance(report, RegimeReport)
    assert report.persona_id == "ray"
    assert len(report.allocations) == 3
    # 0.30 weight would fail Proposal's 0.20 cap but is valid for RegimeAllocation (0.40 cap)
    assert report.allocations[0].target_weight == 0.30


def test_parse_llm_json_skips_leading_prose():
    """Construction RETRIES prefix the JSON with an explanation of what
    changed (4-for-4 on 2026-06-12, killing warren+cathie's rebalance).
    Leading prose — including braces inside it — must be skipped."""
    from tessera_worker.agents.anthropic_runner import parse_llm_json

    raw = (
        "Looking at the feedback, the {sector} cap was breached, so I "
        "trimmed JPM and MCO.\n\n"
        '{"cash_target": 0.2, "proposals": []}\n'
        "This book now respects the 50% cap."
    )
    obj = parse_llm_json(raw)
    assert obj == {"cash_target": 0.2, "proposals": []}


def test_parse_llm_json_still_raises_on_no_json():
    import json as _json

    import pytest as _pt

    from tessera_worker.agents.anthropic_runner import parse_llm_json

    with _pt.raises(_json.JSONDecodeError):
        parse_llm_json("no json here at all, just {broken prose")


def test_build_regime_report_overrides_llm_supplied_as_of():
    """as_of / persona_id are server-authoritative. Ray's Sonnet output
    reliably volunteers an `as_of` of its own (2025-01-24 in prod, copied
    from context/training) — setdefault let it win, stamping every Ray
    row with a 17-month-old book date. Force-set must win instead."""
    import datetime as _dt
    report = build_regime_report(
        {
            "as_of": "2025-01-24",        # LLM-volunteered — must lose
            "persona_id": "warren",       # LLM nonsense — must lose
            "regime": {
                "goldilocks_prob": 0.45, "reflation_prob": 0.30,
                "stagflation_prob": 0.15, "deflation_prob": 0.10,
                "delta_from_last_week_md": "no change.",
            },
            "allocations": [
                {"asset_class": "US equities", "instrument": "VTI",
                 "target_weight": 0.30, "thesis_md": "A" * 25},
            ],
            "cash_target": 0.70,
            "notes_to_manager": "x",
        },
        as_of=_dt.date(2026, 6, 12),
        inputs_hash="hash123",
        model="claude-sonnet-4-6",
        tokens_in=100,
        tokens_out=100,
        cost_usd=0.001,
    )
    assert report.as_of == _dt.date(2026, 6, 12)
    assert report.persona_id == "ray"


def test_build_regime_report_rejects_weights_over_one():
    import datetime as _dt

    import pytest as _pt
    from pydantic import ValidationError as _VE
    with _pt.raises(_VE):
        build_regime_report(
            {
                "regime": {
                    "goldilocks_prob": 0.25, "reflation_prob": 0.25,
                    "stagflation_prob": 0.25, "deflation_prob": 0.25,
                    "delta_from_last_week_md": "no change.",
                },
                "allocations": [
                    {"asset_class": "US equities", "instrument": "VTI",
                     "target_weight": 0.40, "thesis_md": "A" * 25},
                    {"asset_class": "Long UST", "instrument": "TLT",
                     "target_weight": 0.40, "thesis_md": "A" * 25},
                ],
                "cash_target": 0.30,  # 0.40 + 0.40 + 0.30 = 1.10 > 1.0
                "notes_to_manager": "x",
            },
            as_of=_dt.date(2026, 6, 4), inputs_hash="h", model="m",
            tokens_in=0, tokens_out=0, cost_usd=0.0,
        )


# ─── Backtest harness primitives (PR #41 D) ────────────────────────────


def test_trading_days_skips_weekends():
    """trading_days walks back, skips Sat/Sun, returns ascending dates."""
    import datetime as _dt

    from tessera_worker.jobs.backtest_harness import trading_days
    # 2026-06-08 = Monday. Walking back 5 trading days: Mon-Fri prev week.
    days = trading_days(_dt.date(2026, 6, 8), 5)
    assert len(days) == 5
    assert all(d.weekday() < 5 for d in days), [d.weekday() for d in days]
    # Ascending
    assert days == sorted(days)
    # Latest is the given end-date if it's a weekday
    assert days[-1] == _dt.date(2026, 6, 8)


def test_run_result_schema_fail_rate():
    from uuid import uuid4

    from tessera_worker.jobs.backtest_harness import RunResult
    r = RunResult(run_id=uuid4(), attempted=100, rejected=3)
    assert abs(r.schema_fail_rate() - 0.03) < 1e-9
    r2 = RunResult(run_id=uuid4(), attempted=0)
    assert r2.schema_fail_rate() == 0.0

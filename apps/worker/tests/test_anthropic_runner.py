"""Unit tests for anthropic_runner helpers (no API)."""

from __future__ import annotations

from uuid import UUID

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


def test_normalize_conviction_passes_through_unknowns():
    """Unparseable values aren't touched — Pydantic raises a clearer error."""
    p = {"conviction": "purple"}
    _normalize_conviction(p)
    assert p["conviction"] == "purple"

    p = {}  # no conviction key
    _normalize_conviction(p)
    assert p == {}


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


def test_build_regime_report_rejects_weights_over_one():
    import datetime as _dt
    import pytest as _pt
    with _pt.raises(Exception):  # ValidationError
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

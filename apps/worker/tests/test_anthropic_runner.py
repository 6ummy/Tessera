"""Unit tests for anthropic_runner helpers (no API)."""

from __future__ import annotations

from uuid import UUID

import pytest

from tessera_worker.agents.anthropic_runner import (
    build_analyst_report,
    estimate_cost_usd,
    parse_llm_json,
)
from tessera_worker.agents.citation_validator import validate_citations
from tessera_worker.agents.models import AnalystReport


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

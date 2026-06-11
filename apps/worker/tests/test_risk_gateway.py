"""Risk gateway tests — the Decision Plane's final pre-persist validation.

The gateway is a pure function over AnalystReport + persona constraints,
so every hard rule is pinnable here without DB or LLM. Sector metadata
comes from the real universe module on purpose: a universe edit that
reclassifies a ticker should surface here, not in production.
"""

from __future__ import annotations

from datetime import date

from tessera_worker.agents.models import AnalystReport, Proposal
from tessera_worker.risk.gateway import gate


def _proposal(ticker: str, weight: float, *, conviction: float = 0.75) -> Proposal:
    return Proposal(
        ticker=ticker,
        side="buy",
        target_weight=weight,
        horizon_days=365,
        conviction=conviction,
        thesis_md="a perfectly reasonable thesis for testing",
    )


def _report(persona: str, proposals: list[Proposal], cash: float) -> AnalystReport:
    return AnalystReport(
        persona_id=persona,
        as_of=date(2026, 6, 11),
        proposals=proposals,
        cash_target=cash,
        inputs_hash="test",
        model="claude-sonnet-4-6",
        tokens_in=1,
        tokens_out=1,
        cost_usd=0.0,
    )


def test_gate_passes_a_coherent_book():
    report = _report("warren", [
        _proposal("AAPL", 0.15),   # Technology
        _proposal("JPM", 0.15),    # Financials
        _proposal("COST", 0.15),   # Consumer Staples
    ], cash=0.55)
    result = gate(report)
    assert result.ok
    assert result.reasons == []


def test_gate_rejects_unknown_ticker():
    report = _report("warren", [_proposal("ZZZZ", 0.10)], cash=0.90)
    result = gate(report)
    assert not result.ok
    assert any("not in universe" in r and "ZZZZ" in r for r in result.reasons)


def test_gate_rejects_sum_violation():
    # 0.18 positions + 0.20 cash = 0.38 — most of the NAV silently
    # missing. (Schema only rejects totals ABOVE 1.0; the gate owns the
    # under-allocation side.)
    report = _report("warren", [_proposal("AAPL", 0.18)], cash=0.20)
    result = gate(report)
    assert not result.ok
    assert any("!= 1.0" in r for r in result.reasons)


def test_gate_rejects_single_name_cap():
    # Warren's cap is 0.18; 0.19 passes the global schema (≤0.20) but
    # must fail the persona gate.
    report = _report("warren", [_proposal("V", 0.19)], cash=0.81)
    result = gate(report)
    assert not result.ok
    assert any("single-name cap" in r and "V" in r for r in result.reasons)


def test_gate_rejects_sector_cap():
    # 3 × 0.17 = 0.51 Technology > Warren's 0.50 sector cap, while every
    # individual position is inside the 0.18 single-name cap — exactly
    # the case normalize_book cannot see.
    report = _report("warren", [
        _proposal("AAPL", 0.17),
        _proposal("MSFT", 0.17),
        _proposal("NVDA", 0.17),
    ], cash=0.49)
    result = gate(report)
    assert not result.ok
    assert len(result.reasons) == 1
    assert "sector 'Technology'" in result.reasons[0]


def test_gate_accumulates_all_reasons():
    """Retry feedback should fix the whole book in one pass — the gate
    must report every violation, not short-circuit on the first."""
    report = _report("warren", [
        _proposal("ZZZZ", 0.19),   # unknown ticker AND over Warren's cap
    ], cash=0.20)                  # AND sum = 0.39
    result = gate(report)
    assert not result.ok
    assert len(result.reasons) == 3


def test_gate_soft_checks_do_not_fail():
    """Cash outside the persona range + active position below the
    conviction floor are logged, never rejected (the normalizer's
    impossible-envelope fallback legitimately exceeds cash_max)."""
    # Peter: cash range 0.05–0.25, min_active_conviction 0.50.
    report = _report("peter", [
        _proposal("COST", 0.10, conviction=0.40),   # below floor
        _proposal("HD", 0.10),
    ], cash=0.80)                                    # above cash_max
    result = gate(report)
    assert result.ok

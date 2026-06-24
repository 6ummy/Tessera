"""Unit tests for persona_batch — the weekly cron's batch runner.

No DB hits; we monkeypatch `run_thesis` + `run_regime_thesis` so the loop
behavior (per-cell error handling, budget cap, dry-run, persona shortlist
iteration) is testable independently of Anthropic.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tessera_worker.jobs.persona_batch import (
    PERSONA_SHORTLISTS,
    BatchResult,
    run_batch,
)


@dataclass
class _FakeReport:
    cost_usd: float = 0.02


def test_dry_run_skips_llm_and_counts_every_cell(monkeypatch) -> None:
    """--dry-run path doesn't import anthropic_runner at all (lazy)."""
    result = run_batch(personas=["warren", "cathie"], dry_run=True)
    assert result.errors == 0
    assert result.total_cost_usd == 0.0
    expected = len(PERSONA_SHORTLISTS["warren"]) + len(PERSONA_SHORTLISTS["cathie"])
    assert result.attempted == expected
    assert result.persisted == expected


def test_dry_run_includes_ray_as_one_cell() -> None:
    result = run_batch(personas=["ray"], dry_run=True)
    assert result.attempted == 1
    assert result.persisted == 1


def test_real_path_accumulates_cost_per_persisted(monkeypatch) -> None:
    """Each successful cell adds its cost_usd to the running total."""
    def _stub_run_thesis(*, persona, ticker, as_of):
        return _FakeReport(cost_usd=0.03)

    def _stub_run_regime(*, as_of):
        return _FakeReport(cost_usd=0.05)

    monkeypatch.setattr(
        "tessera_worker.agents.anthropic_runner.run_thesis", _stub_run_thesis,
        raising=False,
    )
    monkeypatch.setattr(
        "tessera_worker.agents.anthropic_runner.run_regime_thesis", _stub_run_regime,
        raising=False,
    )

    result = run_batch(personas=["warren", "ray"], max_cost=100.0)
    n_warren = len(PERSONA_SHORTLISTS["warren"])
    assert result.persisted == n_warren + 1
    expected_cost = n_warren * 0.03 + 0.05
    assert abs(result.total_cost_usd - expected_cost) < 1e-6


def test_max_cost_aborts_mid_batch(monkeypatch) -> None:
    """When the running total crosses --max-cost, the loop bails immediately
    instead of paying for the remaining cells."""
    def _stub_run_thesis(*, persona, ticker, as_of):
        return _FakeReport(cost_usd=0.10)

    monkeypatch.setattr(
        "tessera_worker.agents.anthropic_runner.run_thesis", _stub_run_thesis,
        raising=False,
    )

    # 10 cells × $0.10 = $1.00 budget. Set cap at $0.35 → ~4 cells then stop.
    result = run_batch(personas=["warren"], max_cost=0.35)
    assert result.persisted <= 5  # exact count depends on > vs >= check timing
    assert result.persisted >= 3
    assert result.aborted_reason is not None
    assert "max-cost" in result.aborted_reason


def test_per_cell_exception_counted_not_raised(monkeypatch) -> None:
    """A cell that throws an unexpected exception is counted as `errors`
    and the loop continues."""
    call_count = {"n": 0}

    def _stub_run_thesis(*, persona, ticker, as_of):
        call_count["n"] += 1
        # First 2 cells fail, rest succeed
        if call_count["n"] <= 2:
            raise RuntimeError("simulated network blip")
        return _FakeReport(cost_usd=0.02)

    monkeypatch.setattr(
        "tessera_worker.agents.anthropic_runner.run_thesis", _stub_run_thesis,
        raising=False,
    )

    result = run_batch(personas=["warren"], max_cost=10.0)
    assert result.errors == 2
    assert result.persisted == len(PERSONA_SHORTLISTS["warren"]) - 2
    assert result.aborted_reason is None  # cell errors don't abort


def test_llm_disabled_aborts_immediately(monkeypatch) -> None:
    """FEATURE_REAL_LLM=false → first cell raises LlmDisabledError → STOP."""
    from tessera_worker.agents.anthropic_runner import LlmDisabledError

    def _stub_run_thesis(*, persona, ticker, as_of):
        raise LlmDisabledError("FEATURE_REAL_LLM=false")

    monkeypatch.setattr(
        "tessera_worker.agents.anthropic_runner.run_thesis", _stub_run_thesis,
        raising=False,
    )

    result = run_batch(personas=["warren"], max_cost=10.0)
    assert result.errors >= 1
    assert result.aborted_reason is not None
    assert "FEATURE_REAL_LLM" in result.aborted_reason
    # Should have stopped after the first failing cell, not continued.
    assert result.attempted == 1


def test_persona_shortlists_cover_stock_pickers() -> None:
    """Schema sanity: the stock-picker personas have shortlists; ray is
    intentionally not in the dict (regime allocator, handled separately)."""
    assert set(PERSONA_SHORTLISTS) == {"warren", "cathie", "peter", "michael"}
    for persona, tickers in PERSONA_SHORTLISTS.items():
        assert len(tickers) >= 5, f"{persona} shortlist suspiciously short"
        assert len(tickers) <= 15, f"{persona} shortlist over budget"
        # No duplicates within a persona
        assert len(set(tickers)) == len(tickers)


def test_batch_result_initial_state() -> None:
    r = BatchResult()
    assert r.attempted == 0
    assert r.persisted == 0
    assert r.errors == 0
    assert r.total_cost_usd == 0.0
    assert r.aborted_reason is None
    assert r.by_persona == {}


def test_unknown_persona_choice_rejected_by_argparse() -> None:
    """argparse `choices` should reject invalid personas before run_batch fires."""
    # We invoke main() via sys argv emulation; argparse should SystemExit(2).
    import sys

    from tessera_worker.jobs.persona_batch import main
    old_argv = sys.argv
    sys.argv = ["persona_batch", "--personas", "warren", "fake_persona"]
    try:
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
    finally:
        sys.argv = old_argv

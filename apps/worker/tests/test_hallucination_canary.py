"""Unit tests for hallucination_canary's invariant checks.

All checks are pure-data — they take a list of {id, persona_id, parsed}
dicts and append to result.violations. No DB hits in these tests.
"""

from __future__ import annotations

from tessera_worker.jobs.hallucination_canary import (
    CAP_ANCHOR_THRESHOLD,
    CanaryResult,
    Violation,
    check_buy_conviction_floor,
    check_citations_resolve,
    check_forbidden_phrases,
    check_no_cap_anchoring,
    check_persona_topic_drift,
    check_weight_distribution,
)


def _book_row(persona: str, weights: list[float], row_id: str = "r1") -> dict:
    return {
        "id": row_id,
        "persona_id": persona,
        "parsed": {
            "proposals": [
                {"ticker": f"T{i}", "target_weight": w}
                for i, w in enumerate(weights)
            ],
        },
    }


# ─── (6) Weight-distribution telemetry / mode collapse ────────────────


def test_weight_mode_collapse_trips_at_three_names_at_cap() -> None:
    # Warren cap 0.18 — three names parked within 1pp of it = §11 signal.
    result = CanaryResult()
    check_weight_distribution(
        [_book_row("warren", [0.18, 0.175, 0.17, 0.05, 0.04])], result)
    assert any(v.check == "weight_mode_collapse" for v in result.violations)


def test_weight_distribution_healthy_book_passes() -> None:
    result = CanaryResult()
    check_weight_distribution(
        [_book_row("warren", [0.18, 0.12, 0.08, 0.05]),       # one at cap: fine
         _book_row("ray", [0.40, 0.40, 0.20], row_id="r2")],  # ray exempt
        result)
    assert result.violations == []


def _row(persona: str, **proposal_kwargs) -> dict:
    """Build a minimal row dict with one proposal for tests."""
    default = {"ticker": "AAPL", "side": "hold", "target_weight": 0.10,
               "conviction": 0.60, "thesis_md": "ok", "cited_news_ids": []}
    default.update(proposal_kwargs)
    return {"id": "row1", "persona_id": persona, "parsed": {"proposals": [default]}}


# ─── (1) Citation resolves ─────────────────────────────────────────────


def test_citation_check_passes_when_all_ids_valid() -> None:
    valid = {"abc-123", "def-456"}
    rows = [_row("warren", cited_news_ids=["abc-123", "def-456"])]
    result = CanaryResult()
    check_citations_resolve(rows, valid, result)
    assert result.passed


def test_citation_check_flags_invented_id() -> None:
    valid = {"abc-123"}
    rows = [_row("cathie", cited_news_ids=["abc-123", "FAKE-999"])]
    result = CanaryResult()
    check_citations_resolve(rows, valid, result)
    assert len(result.violations) == 1
    assert "FAKE-999" in result.violations[0].detail
    assert result.violations[0].check == "citation_resolves"


def test_citation_check_handles_empty_cites() -> None:
    rows = [_row("warren", cited_news_ids=[])]
    result = CanaryResult()
    check_citations_resolve(rows, set(), result)
    assert result.passed


# ─── (2) No cap anchoring ──────────────────────────────────────────────


def test_cap_anchoring_passes_below_threshold() -> None:
    rows = [_row("warren", target_weight=0.18)]
    result = CanaryResult()
    check_no_cap_anchoring(rows, result)
    # 0.18 < 0.19 threshold
    assert result.passed


def test_cap_anchoring_flags_at_threshold() -> None:
    rows = [_row("cathie", target_weight=0.19)]
    result = CanaryResult()
    check_no_cap_anchoring(rows, result)
    assert len(result.violations) == 1
    assert "0.19" in result.violations[0].detail or "0.1900" in result.violations[0].detail


def test_cap_anchoring_flags_at_cap() -> None:
    """The canonical mode-collapse case: every position pinned at the cap."""
    rows = [_row("warren", target_weight=0.20)]
    result = CanaryResult()
    check_no_cap_anchoring(rows, result)
    assert len(result.violations) == 1


def test_cap_anchoring_handles_missing_weight() -> None:
    rows = [{"id": "r", "persona_id": "warren",
             "parsed": {"proposals": [{"ticker": "AAPL", "side": "hold"}]}}]
    result = CanaryResult()
    check_no_cap_anchoring(rows, result)
    assert result.passed


# ─── (3) Buy conviction floor ──────────────────────────────────────────


def test_conviction_floor_passes_when_buy_has_high_conv() -> None:
    rows = [_row("warren", side="buy", conviction=0.60)]
    result = CanaryResult()
    check_buy_conviction_floor(rows, result)
    assert result.passed


def test_conviction_floor_flags_low_conviction_buy() -> None:
    """Warren floor 0.55; buying at 0.40 is 'I dunno but let's buy anyway'."""
    rows = [_row("warren", side="buy", conviction=0.40)]
    result = CanaryResult()
    check_buy_conviction_floor(rows, result)
    assert len(result.violations) == 1
    assert "conviction=0.40" in result.violations[0].detail


def test_conviction_floor_passes_low_conviction_hold() -> None:
    """Hold doesn't trigger the floor — only buy/add."""
    rows = [_row("warren", side="hold", conviction=0.30)]
    result = CanaryResult()
    check_buy_conviction_floor(rows, result)
    assert result.passed


def test_conviction_floor_includes_add_side() -> None:
    rows = [_row("peter", side="add", conviction=0.40)]
    result = CanaryResult()
    check_buy_conviction_floor(rows, result)
    assert len(result.violations) == 1


def test_conviction_floor_skips_unknown_persona() -> None:
    """Ray has no entry in PERSONA_MIN_BUY_CONVICTION (uses RegimeReport)."""
    rows = [_row("ray", side="buy", conviction=0.10)]
    result = CanaryResult()
    check_buy_conviction_floor(rows, result)
    assert result.passed  # no floor defined for ray


# ─── (4) Forbidden compliance phrases ──────────────────────────────────


def test_forbidden_phrase_clean_thesis_passes() -> None:
    rows = [_row("warren", thesis_md="AAPL has a durable moat. 5y TAM growing.")]
    result = CanaryResult()
    check_forbidden_phrases(rows, result)
    assert result.passed


def test_forbidden_phrase_flags_guaranteed() -> None:
    rows = [_row("cathie", thesis_md="NVDA is a guaranteed return at these levels.")]
    result = CanaryResult()
    check_forbidden_phrases(rows, result)
    assert len(result.violations) == 1
    assert "guaranteed return" in result.violations[0].detail


def test_forbidden_phrase_flags_cant_lose() -> None:
    rows = [_row("peter", thesis_md="At $310 you can't lose on AAPL.")]
    result = CanaryResult()
    check_forbidden_phrases(rows, result)
    assert len(result.violations) >= 1


def test_forbidden_phrase_case_insensitive() -> None:
    rows = [_row("warren", thesis_md="This is a SURE THING. RISK-FREE entry.")]
    result = CanaryResult()
    check_forbidden_phrases(rows, result)
    # Two phrases hit: 'sure thing' + 'risk-free'
    assert len(result.violations) >= 2


# ─── (5) Persona topic drift (options/leverage for value voices) ───────


def test_topic_drift_warren_clean_passes() -> None:
    rows = [_row("warren", thesis_md="AAPL FCF yield 6%, durable moat, 5y hold.")]
    result = CanaryResult()
    check_persona_topic_drift(rows, result)
    assert result.passed


def test_topic_drift_warren_options_flagged() -> None:
    """Warren's spec excludes options — this is spec drift."""
    rows = [_row("warren",
                 thesis_md="A covered call strategy on AAPL would yield extra income.")]
    result = CanaryResult()
    check_persona_topic_drift(rows, result)
    assert len(result.violations) == 1
    assert "covered call" in result.violations[0].detail


def test_topic_drift_cathie_options_ok() -> None:
    """Cathie has no forbidden-topic list — disruption thesis can reference
    derivative markets without spec drift."""
    rows = [_row("cathie",
                 thesis_md="Options activity in NVDA suggests institutional buying.")]
    result = CanaryResult()
    check_persona_topic_drift(rows, result)
    assert result.passed


def test_topic_drift_peter_leverage_flagged() -> None:
    rows = [_row("peter",
                 thesis_md="A leveraged position in HD would amplify the cycle.")]
    result = CanaryResult()
    check_persona_topic_drift(rows, result)
    assert len(result.violations) == 1


# ─── Result aggregation ────────────────────────────────────────────────


def test_canary_result_passed_when_no_violations() -> None:
    r = CanaryResult(rows_checked=10)
    assert r.passed
    assert r.by_check() == {}


def test_canary_result_failed_when_violations_exist() -> None:
    r = CanaryResult(rows_checked=10)
    r.violations.append(Violation(check="x", row_id="r", persona="warren",
                                   ticker="AAPL", detail="bad"))
    assert not r.passed
    assert r.by_check() == {"x": 1}


def test_cap_anchor_threshold_is_below_schema_cap() -> None:
    """Sanity: threshold must leave a safety buffer below the schema cap (0.20)
    so legitimately-near-cap positions don't false-positive."""
    assert CAP_ANCHOR_THRESHOLD < 0.20
    assert CAP_ANCHOR_THRESHOLD >= 0.15  # but not too lenient

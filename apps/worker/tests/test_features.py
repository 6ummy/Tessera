"""Property-based tests on feature math.

Risk Register #11 (feature builder bug propagates as LLM-blessed thesis) is the
reason these exist. Generative tests find edge cases (flat lines, all-up,
all-down, zero volume, single-day series) that hand-written cases miss.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from tessera_worker.features.compute import (
    ADR_SHARE_RATIOS,
    FCF_YIELD_SANITY_BOUND,
    FX_TO_USD,
    RSI_WINDOW,
    VOL_WINDOW,
    VOLUME_Z_WINDOW,
    _market_cap_from_shares,
    compute_fcf_yield,
    cross_validated,
    estimate_market_cap,
    pct_change,
    realized_vol,
    rsi,
    sma,
    sum_ttm_fcf,
    volume_zscore,
)


# Reasonable price series: positive, finite, lengths 30..400.
price_series = st.lists(
    st.floats(min_value=1.0, max_value=1_000.0, allow_nan=False, allow_infinity=False),
    min_size=30,
    max_size=400,
).map(lambda xs: pd.Series(xs, dtype="float64"))

# Volume series matching price length, non-negative integers.
def _volume_for(length: int) -> st.SearchStrategy[pd.Series]:
    return st.lists(
        st.integers(min_value=0, max_value=10_000_000), min_size=length, max_size=length
    ).map(lambda xs: pd.Series(xs, dtype="float64"))


# ─── pct_change ────────────────────────────────────────────────────────
@given(price_series, st.integers(min_value=1, max_value=20))
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_pct_change_first_n_are_nan(close: pd.Series, n: int) -> None:
    if len(close) <= n:
        return
    out = pct_change(close, n)
    assert out.iloc[:n].isna().all(), "first N values must be NaN (no prior reference)"


@given(price_series, st.integers(min_value=1, max_value=20))
def test_pct_change_matches_definition(close: pd.Series, n: int) -> None:
    if len(close) <= n:
        return
    out = pct_change(close, n)
    expected = close.iloc[n] / close.iloc[0] - 1.0
    assert out.iloc[n] == pytest.approx(expected, rel=1e-9)


def test_pct_change_constant_series_is_zero() -> None:
    out = pct_change(pd.Series([100.0] * 50), 5)
    valid = out.dropna()
    assert (valid == 0.0).all()


# ─── realized_vol ──────────────────────────────────────────────────────
def test_vol_of_constant_series_is_zero() -> None:
    out = realized_vol(pd.Series([100.0] * 60), window=VOL_WINDOW)
    assert out.dropna().iloc[-1] == 0.0


@given(price_series)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=30)
def test_vol_is_non_negative(close: pd.Series) -> None:
    if len(close) < VOL_WINDOW + 1:
        return
    out = realized_vol(close, VOL_WINDOW)
    valid = out.dropna()
    assert (valid >= 0.0).all(), "vol cannot be negative"


# ─── rsi ───────────────────────────────────────────────────────────────
def test_rsi_pure_uptrend_saturates() -> None:
    # Strictly increasing → RSI must approach 100, never below 50
    out = rsi(pd.Series(list(range(1, 100)), dtype="float64"), RSI_WINDOW)
    last = out.dropna().iloc[-1]
    assert last >= 95.0, f"strict uptrend should give RSI ≥ 95, got {last}"


def test_rsi_pure_downtrend_saturates() -> None:
    out = rsi(pd.Series(list(range(100, 1, -1)), dtype="float64"), RSI_WINDOW)
    last = out.dropna().iloc[-1]
    assert last <= 5.0, f"strict downtrend should give RSI ≤ 5, got {last}"


@given(price_series)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=30)
def test_rsi_bounded_0_100(close: pd.Series) -> None:
    if len(close) < RSI_WINDOW + 1:
        return
    out = rsi(close, RSI_WINDOW)
    valid = out.dropna()
    assert ((valid >= 0.0) & (valid <= 100.0)).all(), "RSI out of [0, 100]"


# ─── sma ────────────────────────────────────────────────────────────────
@given(price_series, st.sampled_from([5, 20, 50]))
def test_sma_lies_between_min_and_max(close: pd.Series, window: int) -> None:
    if len(close) < window:
        return
    out = sma(close, window)
    for i in range(window - 1, len(close)):
        win = close.iloc[i - window + 1 : i + 1]
        if out.iloc[i] != out.iloc[i]:  # NaN guard
            continue
        assert win.min() <= out.iloc[i] <= win.max()


def test_sma_of_constant_equals_constant() -> None:
    out = sma(pd.Series([42.0] * 50), 20)
    assert out.dropna().iloc[-1] == pytest.approx(42.0)


# ─── volume_zscore ─────────────────────────────────────────────────────
def test_volume_z_flat_volume_is_nan() -> None:
    # Constant volume → std == 0 → z-score undefined (NaN by design)
    out = volume_zscore(pd.Series([1_000_000.0] * 80), VOLUME_Z_WINDOW)
    assert out.iloc[-1] != out.iloc[-1]  # NaN check (NaN != NaN)


def test_volume_z_spike_is_positive() -> None:
    vol = pd.Series([1_000.0] * 79 + [1_000_000.0])  # huge spike on last day
    out = volume_zscore(vol, VOLUME_Z_WINDOW)
    last = out.iloc[-1]
    assert last > 5.0, f"large spike should give z > 5, got {last}"


# ─── Cross-check: log-return vs simple-return tiny case ────────────────
def test_pct_change_and_log_return_close_for_small_moves() -> None:
    # For small daily moves, simple return ≈ log return.
    close = pd.Series([100.0, 100.1, 100.2, 100.3], dtype="float64")
    simple = pct_change(close, 1).dropna().to_numpy()
    log_ret = np.log(close / close.shift(1)).dropna().to_numpy()
    np.testing.assert_allclose(simple, log_ret, atol=1e-4)


# ─── Fundamentals: fcf_yield + ADR correction ──────────────────────────
# Risk Register #11 manifested here as TSM fcf_yield ≈ 48% in the Phase A
# demo — the ADR-vs-common-share unit mismatch. These tests pin the fix.


def test_fcf_yield_basic_us_domiciled() -> None:
    """AAPL-shaped inputs: ratio defaults to 1, simple close × shares."""
    yld = compute_fcf_yield(
        close=230.0, fcf_local=100e9, shares_common=15.2e9, ticker="AAPL",
    )
    assert yld is not None
    assert 0.02 < yld < 0.04, f"expected ~3% for AAPL-shaped inputs, got {yld:.4f}"


def test_fcf_yield_uses_fresh_price_x_shares_not_stale_payload_mcap() -> None:
    """Regression: v1 of the fix preferred payload `marketCap` (stale —
    only updates on filing). LLM voice needs today's-price-aware yield.
    Verify close × shares wins over payload_market_cap when both exist.
    """
    # Real today: close=$230, shares=15.2B → mcap=$3.50T → yield=$100B/$3.5T = 2.86%
    # Stale (from filing 3 months ago): mcap=$3.0T → yield=$100B/$3.0T = 3.33%
    # Correct behavior: use the fresh mcap, get 2.86%
    yld = compute_fcf_yield(
        close=230.0, fcf_local=100e9, shares_common=15.2e9,
        payload_market_cap=3.0e12,     # stale; must be ignored
        ticker="AAPL",
    )
    assert yld is not None
    assert abs(yld - (100e9 / (230.0 * 15.2e9))) < 1e-9


def test_fcf_yield_falls_back_to_payload_mcap_when_shares_missing() -> None:
    """If we can't compute close × shares, fall back rather than drop."""
    yld = compute_fcf_yield(
        close=230.0, fcf_local=100e9, shares_common=None,
        payload_market_cap=3.0e12,
        ticker="AAPL",
    )
    assert yld is not None
    assert abs(yld - (100e9 / 3.0e12)) < 1e-9


def test_fcf_yield_tsm_with_twd_to_usd_conversion() -> None:
    """TSM reports FCF in TWD. Verify currency conversion + that FMP-shaped
    ADR-equivalent share counts produce a sane yield without double-divide.
    Real-world values circa 2026: close ~$437 (ADR), shares basic from
    FMP ~5.19B (already ADR-equivalent), TTM FCF 1097B TWD ≈ $34.3B USD,
    mcap ≈ $2.27T → ~1.5% yield.
    """
    yld = compute_fcf_yield(
        close=437.0,
        fcf_local=1097e9,                 # 1097B TWD
        shares_basic=5.19e9,              # FMP-shape: already ADR-equivalent
        shares_diluted=5.19e9,
        reported_currency="TWD",
        ticker="TSM",
    )
    assert yld is not None
    # Real TSM TTM yield mid-2026: ~1-2%
    assert 0.005 < yld < 0.03, f"TSM TWD-converted yield outside band: {yld:.4f}"


def test_fcf_yield_unknown_currency_drops_safely() -> None:
    """Don't guess on unknown ISO codes — drop rather than ship garbage."""
    yld = compute_fcf_yield(
        close=100.0, fcf_local=10e9, shares_common=1e9,
        reported_currency="XYZ",  # not in FX_TO_USD
        ticker="UNKNOWN",
    )
    assert yld is None


def test_fcf_yield_negative_fcf_yields_negative_number() -> None:
    """Cash-burning growth names: negative FCF, negative yield. Not an error."""
    yld = compute_fcf_yield(
        close=120.0, fcf_local=-5e9, shares_common=1.0e9, ticker="PLTR",
    )
    assert yld is not None
    assert yld < 0


def test_fcf_yield_missing_inputs_return_none() -> None:
    assert compute_fcf_yield(close=None, fcf_local=10e9, shares_common=1e9) is None
    assert compute_fcf_yield(close=100.0, fcf_local=None, shares_common=1e9) is None
    # close + shares both missing AND no payload → drop
    assert compute_fcf_yield(close=None, fcf_local=10e9, shares_common=None) is None


def test_fcf_yield_sanity_bound_drops_garbage() -> None:
    """If a units bug produces a yield beyond ±100%, drop with a warning."""
    yld = compute_fcf_yield(
        close=5.0, fcf_local=10e9, shares_common=1e6, ticker="TEST",
    )
    assert yld is None


def test_adr_ratio_lookup_defaults_to_one_for_unknown_ticker() -> None:
    assert ADR_SHARE_RATIOS.get("UNKNOWN_TICKER_XYZ", 1) == 1
    mcap = _market_cap_from_shares(100.0, 1e9, ticker="UNKNOWN_XYZ")
    assert mcap == 100e9


def test_adr_ratio_dict_is_empty_for_fmp_provider() -> None:
    """ADR_SHARE_RATIOS is empty because FMP, our provider, returns
    ADR-equivalent share counts (not foreign-issuer common totals).
    Dividing again would double-divide. The dict is kept as a hook for
    future providers that report common shares — populate only with
    ground-truth verification."""
    assert ADR_SHARE_RATIOS == {}


# ─── TTM rollup ────────────────────────────────────────────────────────


def test_ttm_sums_four_quarters() -> None:
    """Genuinely quarterly data (provider returns standalone Q values).
    Values are close to each other (ratio < 2.5) so cumulative detection
    doesn't fire."""
    rows = [
        {"freeCashFlow": 30e9, "period": "Q2"},
        {"freeCashFlow": 25e9, "period": "Q1"},
        {"freeCashFlow": 28e9, "period": "Q3"},
        {"freeCashFlow": 22e9, "period": "Q3"},
        {"freeCashFlow": 27e9, "period": "Q2"},
    ]
    assert sum_ttm_fcf(rows) == 30e9 + 25e9 + 28e9 + 22e9


def test_ttm_returns_annual_when_latest_is_FY() -> None:
    """Issuers that file annually (some foreign cos): latest row is FY,
    which is already TTM — return it directly."""
    rows = [
        {"freeCashFlow": 870e9, "period": "FY"},  # newest
        {"freeCashFlow": 286e9, "period": "FY"},
        {"freeCashFlow": 521e9, "period": "FY"},
    ]
    assert sum_ttm_fcf(rows) == 870e9


def test_ttm_skips_fy_when_mixing_with_quarterlies() -> None:
    """Don't double-count: if quarterlies are present, ignore FY rows."""
    rows = [
        {"freeCashFlow": 30e9, "period": "Q2"},
        {"freeCashFlow": 100e9, "period": "FY"},   # skip
        {"freeCashFlow": 25e9, "period": "Q1"},
        {"freeCashFlow": 28e9, "period": "Q4"},
        {"freeCashFlow": 22e9, "period": "Q3"},
    ]
    assert sum_ttm_fcf(rows) == 105e9


def test_ttm_fewer_than_four_quarters_returns_none() -> None:
    """Partial-year FCF is misleading — drop rather than under-report."""
    rows = [
        {"freeCashFlow": 30e9, "period": "Q2"},
        {"freeCashFlow": 25e9, "period": "Q1"},
        {"freeCashFlow": 28e9, "period": "Q4"},
    ]
    assert sum_ttm_fcf(rows) is None


def test_ttm_handles_null_period_as_quarterly() -> None:
    """Real DB rows often have period=None (provider didn't fill it).
    Treat as quarterly so US-listed names work."""
    rows = [
        {"freeCashFlow": 30e9, "period": None},
        {"freeCashFlow": 25e9, "period": None},
        {"freeCashFlow": 28e9, "period": None},
        {"freeCashFlow": 22e9, "period": None},
    ]
    assert sum_ttm_fcf(rows) == 105e9


def test_ttm_empty_input_returns_none() -> None:
    assert sum_ttm_fcf([]) is None


def test_ttm_detects_cumulative_ytd_aapl_shape() -> None:
    """FMP returns AAPL freeCashFlow as cumulative-since-FY-start:
       Q1 ≈ 3 months of FCF, Q2 ≈ 6 months, ... Q4/FY ≈ 12 months.
       Summing those triple-counts. Our detector should see the wide
       max/min ratio across a 6-row window and return MAX (= last
       FY-end annual value) instead of summing.
    """
    # Pattern mirroring real AAPL data observed in DB (period unspecified)
    rows = [
        {"freeCashFlow": 78.28e9, "period": None},  # Q2 FY26 YTD
        {"freeCashFlow": 51.55e9, "period": None},  # Q1 FY26 YTD
        {"freeCashFlow": 98.77e9, "period": None},  # Q4 FY25 = FY annual
        {"freeCashFlow": 72.28e9, "period": None},  # Q3 FY25 YTD
        {"freeCashFlow": 47.88e9, "period": None},  # Q2 FY25 YTD
        {"freeCashFlow": 27.00e9, "period": None},  # Q1 FY25 YTD
    ]
    result = sum_ttm_fcf(rows)
    # Should return MAX = 98.77B (FY25 annual), NOT sum = 376B (triple-count)
    assert result == 98.77e9
    assert result < 200e9, "sum-based answer would exceed any real AAPL TTM"


def test_ttm_q4_period_is_treated_as_annual() -> None:
    """Q4 period is full-year cumulative — same as FY shortcut."""
    rows = [{"freeCashFlow": 100e9, "period": "Q4"}]
    assert sum_ttm_fcf(rows) == 100e9


# ─── FX table sanity ───────────────────────────────────────────────────


def test_fx_table_has_universe_currencies() -> None:
    """Currencies for any ticker in the universe must be in the FX table.
    Adding a foreign issuer? Add its currency here too."""
    for ccy in ("USD", "TWD", "EUR"):  # known universe-relevant
        assert ccy in FX_TO_USD


def test_fx_usd_is_identity() -> None:
    assert FX_TO_USD["USD"] == 1.0


# ─── build() toggle ────────────────────────────────────────────────────


# ─── Cross-validation primitive ────────────────────────────────────────


def test_cross_validated_single_candidate() -> None:
    assert cross_validated([("only", 100.0)]) == 100.0


def test_cross_validated_no_valid_candidates() -> None:
    assert cross_validated([("none", None), ("zero", 0)]) is None  # type: ignore[list-item]


def test_cross_validated_agreement_returns_first() -> None:
    """When all candidates agree (within max_spread), trust the first
    (caller orders by trust priority)."""
    result = cross_validated([("trust1", 100.0), ("trust2", 110.0), ("trust3", 120.0)])
    assert result == 100.0  # first wins because spread 120/100=1.2 < 2.0


def test_cross_validated_disagreement_picks_max() -> None:
    """When spread > 2× (default), pick max as the conservative choice."""
    # 100 vs 500 → spread 5× → disagreement → max
    result = cross_validated([("under", 100.0), ("over", 500.0)])
    assert result == 500.0


def test_cross_validated_disagreement_pick_min_when_configured() -> None:
    result = cross_validated(
        [("a", 100.0), ("b", 500.0)],
        pick_on_disagreement="min",
    )
    assert result == 100.0


# ─── Market cap estimation — the systemic fix ──────────────────────────


def test_estimate_market_cap_all_agree() -> None:
    """Realistic AAPL: 4 candidates, all within 2×. Returns close×diluted
    (first / most-trusted)."""
    mcap = estimate_market_cap(
        close=230.0,
        shares_basic=14.67e9,    # close × basic = $3.37T
        shares_diluted=14.73e9,  # close × dil   = $3.39T  ← preferred
        payload_mcap_cash=3.4e12,
        payload_mcap_income=3.45e12,
        ticker="AAPL",
    )
    assert mcap is not None
    expected = 230.0 * 14.73e9
    assert abs(mcap - expected) < 1.0


def test_estimate_market_cap_disagreement_picks_max() -> None:
    """If close × shares severely undercounts vs payload mcap (or vice
    versa), pick the bigger — yields a CONSERVATIVE fcf_yield."""
    # close×shares would give $1.5T (under), payload says $3.5T (real-ish).
    # Spread = 3.5/1.5 = 2.33 > 2.0 → disagreement → max
    mcap = estimate_market_cap(
        close=230.0,
        shares_basic=6.5e9,        # close × basic = $1.50T (undercount)
        shares_diluted=6.6e9,
        payload_mcap_cash=3.5e12,
        payload_mcap_income=3.5e12,
        ticker="AAPL_LIKE",
    )
    assert mcap == 3.5e12


def test_estimate_market_cap_only_payload_available() -> None:
    """If shares are missing, fall back to payload."""
    mcap = estimate_market_cap(
        close=None, shares_basic=None, shares_diluted=None,
        payload_mcap_cash=3.5e12, payload_mcap_income=None,
        ticker="X",
    )
    assert mcap == 3.5e12


def test_estimate_market_cap_only_shares_available() -> None:
    """If payload mcap is missing, use close × shares."""
    mcap = estimate_market_cap(
        close=100.0, shares_basic=1e9, shares_diluted=1.01e9,
        payload_mcap_cash=None, payload_mcap_income=None,
        ticker="X",
    )
    assert mcap == 100.0 * 1.01e9  # diluted preferred


def test_estimate_market_cap_no_candidates_returns_none() -> None:
    assert estimate_market_cap(
        close=None, shares_basic=None, shares_diluted=None,
        payload_mcap_cash=None, payload_mcap_income=None,
    ) is None


def test_fcf_yield_uses_cross_validated_mcap_end_to_end() -> None:
    """The TSM-shaped scenario: shares from FMP look like ADR-equivalent,
    so close × shares undercounts; payload mcap reflects true USD mcap.
    Cross-validation picks the higher one → conservative fcf_yield.
    """
    # Hypothetical: close × shares = $200B, payload = $450B → disagreement
    # → mcap = $450B. fcf_local 1097B TWD = $34.3B USD → yield = 7.6%
    yld = compute_fcf_yield(
        close=180.0,
        fcf_local=1097e9,
        shares_basic=1.04e9,           # gives $187B (×1)
        shares_diluted=1.04e9,
        reported_currency="TWD",
        payload_mcap_cash=450e9,       # gives $450B
        ticker="TSM_LIKE",
    )
    assert yld is not None
    # With max=$450B mcap: 34.3 / 450 = 7.6% ✓
    assert 0.05 < yld < 0.10


# ─── Back-compat — legacy callers ──────────────────────────────────────


def test_legacy_kwarg_shares_common_still_works() -> None:
    """Older callers / tests pass shares_common= and payload_market_cap=.
    These are accepted as aliases for shares_basic / payload_mcap_cash."""
    yld = compute_fcf_yield(
        close=230.0, fcf_local=100e9,
        shares_common=14.7e9,              # legacy positional alias
        payload_market_cap=3.4e12,         # legacy alias
        ticker="AAPL",
    )
    assert yld is not None
    assert 0.025 < yld < 0.035


def test_build_signature_accepts_with_fundamentals_toggle() -> None:
    """API contract — orchestrators rely on this kwarg to flex cadence.
    No DB hit; just verify the signature accepts the flag."""
    import inspect
    from tessera_worker.features.compute import build
    sig = inspect.signature(build)
    assert "with_fundamentals" in sig.parameters
    assert sig.parameters["with_fundamentals"].default is True

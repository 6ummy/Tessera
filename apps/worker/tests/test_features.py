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
    """TSM reports FCF in TWD. Real bug: 1097B TWD treated as USD blew
    the yield up to 242%, sanity bound dropped it. With correct FX:
    1097B TWD × (1/32) ≈ $34.3B USD; mcap ≈ $933B → ~3.7% yield.
    """
    yld = compute_fcf_yield(
        close=180.0,
        fcf_local=1097e9,                 # 1097B TWD
        shares_common=25.93e9,
        reported_currency="TWD",
        ticker="TSM",
    )
    assert yld is not None
    # Real TSM yield: low-to-mid single digit %
    assert 0.02 < yld < 0.08, f"TSM TWD-converted yield outside band: {yld:.4f}"


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


def test_adr_ratio_present_for_known_adrs() -> None:
    assert ADR_SHARE_RATIOS["TSM"] == 5
    assert ADR_SHARE_RATIOS["ASML"] == 1


# ─── TTM rollup ────────────────────────────────────────────────────────


def test_ttm_sums_four_quarters() -> None:
    rows = [
        {"freeCashFlow": 30e9, "period": "Q2"},
        {"freeCashFlow": 25e9, "period": "Q1"},
        {"freeCashFlow": 28e9, "period": "Q4"},
        {"freeCashFlow": 22e9, "period": "Q3"},
        {"freeCashFlow": 15e9, "period": "Q2"},  # 5th — should be ignored
    ]
    assert sum_ttm_fcf(rows) == 105e9


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


# ─── FX table sanity ───────────────────────────────────────────────────


def test_fx_table_has_universe_currencies() -> None:
    """Currencies for any ticker in the universe must be in the FX table.
    Adding a foreign issuer? Add its currency here too."""
    for ccy in ("USD", "TWD", "EUR"):  # known universe-relevant
        assert ccy in FX_TO_USD


def test_fx_usd_is_identity() -> None:
    assert FX_TO_USD["USD"] == 1.0


# ─── build() toggle ────────────────────────────────────────────────────


def test_build_signature_accepts_with_fundamentals_toggle() -> None:
    """API contract — orchestrators rely on this kwarg to flex cadence.
    No DB hit; just verify the signature accepts the flag."""
    import inspect
    from tessera_worker.features.compute import build
    sig = inspect.signature(build)
    assert "with_fundamentals" in sig.parameters
    assert sig.parameters["with_fundamentals"].default is True

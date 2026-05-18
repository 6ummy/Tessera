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
    RSI_WINDOW,
    VOL_WINDOW,
    VOLUME_Z_WINDOW,
    pct_change,
    realized_vol,
    rsi,
    sma,
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

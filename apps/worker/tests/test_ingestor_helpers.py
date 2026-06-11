"""Pure-helper tests for the yfinance ingestors (audit Step 3-⑥).

The ingestors themselves are network-bound; their symbol/label/number
normalization helpers are not — and those are exactly where Yahoo's
conventions diverge from ours (dual-class dots vs dashes, NaN-encoded
gaps, drifting row labels)."""

from __future__ import annotations

import pandas as pd

from tessera_worker.ingestors.yf_history import (
    EPS_LABELS,
    _pick_label,
    _safe_float,
)
from tessera_worker.ingestors.yf_history import (
    _to_yahoo_symbol as hist_symbol,
)
from tessera_worker.ingestors.yf_shares import _to_yahoo_symbol as shares_symbol


def test_yahoo_symbol_mapping_dual_class():
    """Yahoo uses '-' for share classes where SEC/Alpaca/universe use '.'.
    Both ingestors must agree (BRK.B was a real coverage gap)."""
    for fn in (shares_symbol, hist_symbol):
        assert fn("BRK.B") == "BRK-B"
        assert fn("AAPL") == "AAPL"


def test_safe_float_filters_nan_and_garbage():
    assert _safe_float(1.5) == 1.5
    assert _safe_float("2.5") == 2.5
    assert _safe_float(float("nan")) is None   # Yahoo encodes gaps as NaN
    assert _safe_float(None) is None
    assert _safe_float("not a number") is None


def test_pick_label_priority_order():
    """First matching label wins — 'Diluted EPS' must beat 'Basic EPS'
    when both exist (Yahoo ships both for most filers)."""
    df = pd.DataFrame(
        {"2025-12-31": [6.1, 6.4]},
        index=["Diluted EPS", "Basic EPS"],
    )
    row = _pick_label(df, EPS_LABELS)
    assert row is not None
    assert row["2025-12-31"] == 6.1


def test_pick_label_returns_none_when_absent():
    df = pd.DataFrame({"2025-12-31": [100.0]}, index=["Total Revenue"])
    assert _pick_label(df, EPS_LABELS) is None

"""Macro sensitivity audit — which FRED series drive which tickers?

For each (ticker, macro series) pair, computes the 60-day rolling
correlation of daily returns. Output: per-ticker top-K macro drivers,
plus a flat list sorted by absolute correlation so Quant can pick
features and LLM Pipeline can build the TICKER_MACRO_OVERLAY dict.

Run:  python -m tessera_worker.features.demo_macro_sensitivity
See:  features/Quant_demo.md  for how this fits the feature pipeline.

Why this exists:
  We ingest 37 FRED series daily, but Warren's prompt only includes 6
  (DGS10, T10YIE, BAMLH0A0HYM2, VIXCLS, DEXCHUS, DCOILWTICO). The other
  31 are dark — present in the DB, not informing any persona. This
  script tells us which dark series each ticker actually responds to,
  so the per-persona / per-ticker macro picks are data-driven instead
  of hand-picked.

Output is suggestion text — paste into agents/LLM_pipeline_demo.md's
TICKER_MACRO_OVERLAY dict or use as input to a new Quant feature
(oil_beta_30d, fx_beta_<pair>_30d, etc.).

Caveats:
  - Correlation != causation. A ticker may correlate with oil for
    reasons (sector beta, common macro driver) that won't generalize.
  - Monthly FRED series (CPI, PCE, payrolls) are forward-filled to
    daily before correlating; the apparent "high correlation" can be
    artifact of slow updates. Treat |r| < 0.20 with skepticism for
    monthly series.
  - Window = 1 year (most recent 252 trading days) so the picture
    reflects current regime, not 20-yr average.
"""

from __future__ import annotations

import contextlib
import sys
import warnings

import pandas as pd
from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.universe import by_asset_class

# Silence "invalid value in divide" from pandas .corr() when a column is
# all-zero (some monthly macros after diff() have stretches of zeros).
# Registered before any .corr() call runs; import order does not matter.
warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")

with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Config ───────────────────────────────────────────────────────────
WINDOW_DAYS = 252  # 1 year of trading days
TOP_K = 5          # top-K macro drivers per ticker
MIN_CORR = 0.15    # below this we treat as noise


# ── Read everything in two pandas pivot tables ──────────────────────
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (returns_df, macro_returns_df) aligned on date."""
    tickers = [t.ticker for t in by_asset_class("equity")]
    with session_scope() as s:
        # Daily close per ticker — dedupe with DISTINCT ON (yahoo > alpaca)
        px = pd.read_sql(text("""
            SELECT DISTINCT ON (ticker, ts::date)
                   ticker, ts::date AS d, close
            FROM ohlcv_1d
            WHERE ticker = ANY(:t) AND ts >= NOW() - INTERVAL '%d days'
            ORDER BY ticker, ts::date,
                     CASE source WHEN 'yahoo' THEN 1 WHEN 'alpaca' THEN 2 ELSE 9 END
        """.replace("%d", str(int(WINDOW_DAYS * 1.5)))),
            s.connection(), params={"t": tickers})
        macros = pd.read_sql(text("""
            SELECT series_id, ts AS d, value
            FROM macro_series
            WHERE ts >= NOW() - INTERVAL '%d days'
        """.replace("%d", str(int(WINDOW_DAYS * 1.5)))),
            s.connection())

    if px.empty or macros.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Pivot prices to ticker columns
    px["d"] = pd.to_datetime(px["d"])
    px_wide = px.pivot(index="d", columns="ticker", values="close").sort_index()
    rets = px_wide.pct_change().dropna(how="all")

    # Pivot macro to series columns; forward-fill for monthly cadence
    macros["d"] = pd.to_datetime(macros["d"])
    macros["value"] = pd.to_numeric(macros["value"], errors="coerce")
    macro_wide = macros.pivot(index="d", columns="series_id", values="value").sort_index()
    macro_wide = macro_wide.ffill(limit=35)  # cover monthly gaps
    # Compute pct-change for level series, raw delta for already-rate series
    macro_rets = macro_wide.pct_change()
    # For yield/spread series (already in pct), use simple diff instead
    rate_like = [c for c in macro_wide.columns
                 if c.startswith("DGS") or c.startswith("T10")
                 or c.startswith("BAML") or c.startswith("CES")
                 or c in ("UNRATE", "VIXCLS")]
    for c in rate_like:
        if c in macro_wide.columns:
            macro_rets[c] = macro_wide[c].diff()
    macro_rets = macro_rets.dropna(how="all")

    # Trim to most recent WINDOW_DAYS trading days for both
    rets = rets.tail(WINDOW_DAYS)
    macro_rets = macro_rets.tail(WINDOW_DAYS)
    return rets, macro_rets


# ── Pairwise correlation, top-K per ticker ─────────────────────────
def correlate(rets: pd.DataFrame, macro_rets: pd.DataFrame) -> pd.DataFrame:
    # Align on date, then corrwith
    rows = []
    for tk in rets.columns:
        s = rets[tk].dropna()
        if len(s) < 60:
            continue
        for mid in macro_rets.columns:
            m = macro_rets[mid].dropna()
            common = s.index.intersection(m.index)
            if len(common) < 60:
                continue
            r = s.loc[common].corr(m.loc[common])
            if pd.isna(r):
                continue
            rows.append({"ticker": tk, "series": mid, "corr": r,
                         "abs": abs(r), "n": len(common)})
    return pd.DataFrame(rows)


# ── Render ──────────────────────────────────────────────────────────
def render_per_ticker(corr_df: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print(f"PER-TICKER TOP-{TOP_K} MACRO DRIVERS  (window: {WINDOW_DAYS} trading days)")
    print("=" * 78)
    if corr_df.empty:
        print("  (no correlations computed — check data depth)")
        return
    for tk in sorted(corr_df["ticker"].unique()):
        sub = (corr_df[(corr_df["ticker"] == tk) & (corr_df["abs"] >= MIN_CORR)]
               .sort_values("abs", ascending=False).head(TOP_K))
        if sub.empty:
            print(f"\n  {tk:<8}  (no series above |r|={MIN_CORR})")
            continue
        print(f"\n  {tk:<8}")
        for _, r in sub.iterrows():
            bar_width = int(abs(r["corr"]) * 20)
            bar = ("#" if r["corr"] > 0 else "=") * bar_width
            print(f"    {r['series']:<22}  r={r['corr']:+.2f}  {bar}")


def render_suggested_overlay(corr_df: pd.DataFrame) -> None:
    """Output a copy-pasteable Python dict for TICKER_MACRO_OVERLAY."""
    print("\n" + "=" * 78)
    print("SUGGESTED TICKER_MACRO_OVERLAY  (top-3 per ticker, paste into agents/)")
    print("=" * 78)
    print()
    print("TICKER_MACRO_OVERLAY = {")
    for tk in sorted(corr_df["ticker"].unique()):
        sub = (corr_df[(corr_df["ticker"] == tk) & (corr_df["abs"] >= MIN_CORR)]
               .sort_values("abs", ascending=False).head(3))
        if sub.empty:
            continue
        series_list = ", ".join(f'"{s}"' for s in sub["series"])
        print(f'    "{tk}":  [{series_list}],')
    print("}")


def render_top_pairs(corr_df: pd.DataFrame, k: int = 20) -> None:
    """Flat top-K pairs across the universe."""
    print("\n" + "=" * 78)
    print(f"TOP {k} CORRELATED (ticker, series) PAIRS GLOBALLY")
    print("=" * 78)
    if corr_df.empty:
        return
    top = corr_df.sort_values("abs", ascending=False).head(k)
    print()
    print(f"  {'rank':>4}  {'ticker':<8}  {'series':<22}  {'r':>6}")
    print(f"  {'-'*4}  {'-'*8}  {'-'*22}  {'-'*6}")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"  {i:>4}  {r['ticker']:<8}  {r['series']:<22}  {r['corr']:+.2f}")


def main() -> int:
    print("Loading prices + macro from Neon...")
    rets, macro_rets = load_data()
    if rets.empty or macro_rets.empty:
        print("ERROR: insufficient data — run backfill_history first.")
        return 1
    print(f"  prices:  {rets.shape[1]} tickers × {len(rets)} days")
    print(f"  macros:  {macro_rets.shape[1]} series  × {len(macro_rets)} days")

    print("\nComputing pairwise correlations...")
    corr_df = correlate(rets, macro_rets)
    print(f"  computed {len(corr_df)} (ticker, series) pairs")

    render_per_ticker(corr_df)
    render_top_pairs(corr_df, k=20)
    render_suggested_overlay(corr_df)

    print("\nTip: this overlay dict updates as the data shifts. Re-run weekly")
    print("during Phase B to keep persona prompts aligned with current regime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

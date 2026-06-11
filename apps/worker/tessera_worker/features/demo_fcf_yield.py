"""FCF yield screen demo — reads from Neon, computes, prints an ASCII bar
chart of the equity universe sorted by FCF yield.

⚠️  This is the Phase A teaching demo, not the production path.

For the actual fcf_yield value the LLM personas read, see:
  - `compute.py: compute_fcf_yield()` — production function with TTM
    rollup (cumulative-YTD decomposition), FX conversion, and cross-
    validated market cap. Wired into `build()` and written to
    `ticker_features.fcf_yield` each daily run.
  - `compute.py: sum_ttm_fcf()` — robust to 3 FMP data shapes.
  - `compute.py: cross_validated()` — agreement primitive reusable
    for the next features in the backlog (PEG, EPS CAGR, etc.).

This demo stays as:
  - A read→compute→print recipe that's ~100 lines and easy to fork.
  - The "extend this" reference target in `Quant_demo.md`.
It uses the SIMPLER naive formula (close × weightedAverageShsOut, no
TTM rollup, no FX conversion) — fine for screen visualization but not
the number the LLM gets. To see what production writes, query
`ticker_features.fcf_yield` directly.

Run:  python -m tessera_worker.features.demo_fcf_yield
See:  features/Quant_demo.md  for context + "extend this" patterns.

Schema notes (fundamentals table):
  ticker | period_end | filing_type ('income'|'balance'|'cash_flow') | payload JSONB

No new dependencies — only pandas + sqlalchemy already in pyproject.
"""

from __future__ import annotations

import contextlib
import sys

import pandas as pd
from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.universe import by_asset_class

# Force UTF-8 stdout so non-ASCII chars don't crash on Windows cp1252.
with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ─────────────────────────────────────────────────────────────────────────
# Read — pull the minimum we need
# ─────────────────────────────────────────────────────────────────────────
def fetch() -> pd.DataFrame:
    tickers = [t.ticker for t in by_asset_class("equity")]

    with session_scope() as session:
        # Latest close per ticker — Timescale handles "most recent" fast
        closes = session.execute(text("""
            SELECT DISTINCT ON (ticker) ticker, close
            FROM ohlcv_1d
            WHERE ticker = ANY(:t)
            ORDER BY ticker, ts DESC
        """), {"t": tickers}).all()
        close_by = {r.ticker: float(r.close) for r in closes}

        # Latest FCF per ticker — pulled from cash_flow filing_type
        fcf_rows = session.execute(text("""
            SELECT DISTINCT ON (ticker) ticker,
                   period_end,
                   payload ->> 'freeCashFlow' AS fcf
            FROM fundamentals
            WHERE ticker = ANY(:t) AND filing_type = 'cash_flow'
            ORDER BY ticker, period_end DESC
        """), {"t": tickers}).all()

        # Latest shares outstanding per ticker — from income filing_type
        sh_rows = session.execute(text("""
            SELECT DISTINCT ON (ticker) ticker,
                   payload ->> 'weightedAverageShsOut' AS shares
            FROM fundamentals
            WHERE ticker = ANY(:t) AND filing_type = 'income'
            ORDER BY ticker, period_end DESC
        """), {"t": tickers}).all()
        shares_by = {r.ticker: r.shares for r in sh_rows}

    # ─────────────────────────────────────────────────────────────────────
    # Compute in pandas — pure, easy to property-test
    # ─────────────────────────────────────────────────────────────────────
    rows = []
    for r in fcf_rows:
        fcf_raw = r.fcf
        shares_raw = shares_by.get(r.ticker)
        if not fcf_raw or not shares_raw:
            continue
        try:
            fcf, shares = float(fcf_raw), float(shares_raw)
        except (TypeError, ValueError):
            continue
        close = close_by.get(r.ticker)
        if not close:
            continue
        mcap = close * shares
        if mcap <= 0:
            continue
        rows.append({
            "ticker":     r.ticker,
            "period_end": r.period_end,
            "close":      close,
            "shares":     shares,
            "mcap":       mcap,
            "fcf":        fcf,
            "fcf_yield":  fcf / mcap,
        })

    return pd.DataFrame(rows).sort_values("fcf_yield", ascending=False)


# ─────────────────────────────────────────────────────────────────────────
# Visual output — ASCII bar chart
# ─────────────────────────────────────────────────────────────────────────
def render(df: pd.DataFrame, bar_width_chars: int = 30) -> str:
    if df.empty:
        return "(no rows — fundamentals or close data missing for the whole universe)"

    pos = df[df["fcf_yield"] > 0]
    max_y = pos["fcf_yield"].max() if not pos.empty else df["fcf_yield"].max()

    lines = [
        "",
        f"=== FCF yield screen ({len(df)} equities with data) ===",
        "",
        f"  {'ticker':<8}  {'bar':<{bar_width_chars}}  {'fcf_yield':>10}  {'mcap (B)':>10}",
        f"  {'-' * 8}  {'-' * bar_width_chars}  {'-' * 10}  {'-' * 10}",
    ]

    for _, r in df.iterrows():
        if r["fcf_yield"] <= 0:
            bar = "(neg)"
        else:
            n_blocks = max(1, int((r["fcf_yield"] / max_y) * bar_width_chars))
            bar = "#" * n_blocks
        lines.append(
            f"  {r['ticker']:<8}  {bar:<{bar_width_chars}}  "
            f"{r['fcf_yield']:>9.2%}  {r['mcap'] / 1e9:>9.1f}"
        )

    if not pos.empty:
        warren_screen = pos[pos["fcf_yield"] >= 0.06]
        lines += [
            "",
            f"  mean (positive):   {pos['fcf_yield'].mean():.2%}",
            f"  median (positive): {pos['fcf_yield'].median():.2%}",
            f"  Warren screen (FCF yield >= 6%): {len(warren_screen)}"
            + (f"  ->  {', '.join(warren_screen['ticker'].head(8).tolist())}"
               if not warren_screen.empty else ""),
        ]
    return "\n".join(lines)


def main() -> int:
    print("Connecting to Neon + computing FCF yield...")
    df = fetch()
    print(render(df))
    print()
    print("Next: write back to ticker_features after a column migration.")
    print("See features/Quant_demo.md -> 'Wire into ticker_features'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

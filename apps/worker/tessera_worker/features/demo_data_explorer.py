"""Data explorer — see what's actually in Neon right now.

After the Phase C pre-ship backfill, the DB has ~6 yrs of equity prices,
~11 yrs of crypto, full FRED macro history, and structured fundamentals
for 39/42 tickers. This script renders ASCII sparklines + coverage
tables so anyone can answer "what data do we have?" in 5 seconds.

Run:  python -m tessera_worker.features.demo_data_explorer
See:  features/Quant_demo.md  for the read->compute->visualize pattern.

Three sections:
  1. Universe coverage matrix    — per-ticker OHLCV + fundamentals depth
  2. Price history sparklines    — visual 6yr trajectory for top names
  3. Macro snapshot              — key FRED series with sparklines

No new deps. Uses Unicode block chars for sparklines (renders in any
modern terminal incl. PowerShell with UTF-8 stdout).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.universe import by_asset_class

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

# 8-level block chars for sparklines. Each char represents one bucket.
SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"


# ─────────────────────────────────────────────────────────────────────────
# Sparkline rendering
# ─────────────────────────────────────────────────────────────────────────
def sparkline(values: list[float], width: int = 40) -> str:
    """Map values to 8 block-char levels. Downsample to `width` points."""
    if not values:
        return "(no data)"
    # Downsample by bucketing
    if len(values) > width:
        bucket = len(values) / width
        out = []
        for i in range(width):
            start = int(i * bucket)
            end = int((i + 1) * bucket)
            chunk = values[start:end]
            if chunk:
                out.append(sum(chunk) / len(chunk))
        values = out
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return SPARKLINE_CHARS[0] * len(values)
    step = (vmax - vmin) / (len(SPARKLINE_CHARS) - 1)
    return "".join(SPARKLINE_CHARS[min(int((v - vmin) / step), 7)] for v in values)


# ─────────────────────────────────────────────────────────────────────────
# Section 1 — universe coverage matrix
# ─────────────────────────────────────────────────────────────────────────
def render_coverage() -> None:
    print("=" * 78)
    print("1. UNIVERSE COVERAGE — what's in Neon today")
    print("=" * 78)
    tickers = [t.ticker for t in by_asset_class("equity")]

    with session_scope() as s:
        # DISTINCT calendar days (yahoo + alpaca may both have rows for
        # the same date at different times-of-day — count once per date).
        ohlcv = {
            r.ticker: r for r in s.execute(text("""
                SELECT ticker,
                       COUNT(DISTINCT ts::date) AS n,
                       MIN(ts) AS first_day,
                       MAX(ts) AS last_day
                FROM ohlcv_1d
                WHERE ticker = ANY(:t)
                GROUP BY ticker
            """), {"t": tickers}).all()
        }
        fund = {
            r.ticker: r for r in s.execute(text("""
                SELECT ticker,
                       COUNT(DISTINCT period_end) AS periods,
                       MIN(period_end) AS first_period,
                       MAX(period_end) AS last_period
                FROM fundamentals
                WHERE ticker = ANY(:t)
                GROUP BY ticker
            """), {"t": tickers}).all()
        }
        filings = {
            r.ticker: r.n for r in s.execute(text("""
                SELECT ticker, COUNT(*) AS n FROM filings
                WHERE ticker = ANY(:t) GROUP BY ticker
            """), {"t": tickers}).all()
        }

    today = date.today()
    print()
    print(f"  {'ticker':<8}  {'OHLCV days':>10}  {'depth':>8}  "
          f"{'fund periods':>13}  {'fund last':>12}  {'filings':>8}")
    print(f"  {'-'*8}  {'-'*10}  {'-'*8}  {'-'*13}  {'-'*12}  {'-'*8}")
    for tk in sorted(tickers):
        o = ohlcv.get(tk)
        f = fund.get(tk)
        fl = filings.get(tk, 0)
        if o:
            depth_yrs = (o.last_day - o.first_day).days / 365.25
            o_str = f"{o.n:>10}  {depth_yrs:>5.1f}yr"
        else:
            o_str = f"{'-':>10}  {'-':>8}"
        if f:
            f_str = f"{f.periods:>13}  {str(f.last_period):>12}"
        else:
            f_str = f"{'-':>13}  {'-':>12}"
        print(f"  {tk:<8}  {o_str}  {f_str}  {fl:>8}")


# ─────────────────────────────────────────────────────────────────────────
# Section 2 — price history sparklines
# ─────────────────────────────────────────────────────────────────────────
def render_price_sparklines(tickers: list[str] | None = None) -> None:
    if tickers is None:
        tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "TSLA",
                   "AMZN", "JPM", "XOM", "BRK.B"]
    print()
    print("=" * 78)
    print("2. PRICE SPARKLINES — full history per ticker")
    print("=" * 78)
    print()
    with session_scope() as s:
        for tk in tickers:
            # Take the deepest history available — prefer Yahoo if present
            # (20 yrs), fall back to Alpaca (6 yrs). DISTINCT ON ensures
            # one close per calendar day even when both sources stored a row.
            rows = s.execute(text("""
                SELECT DISTINCT ON (ts::date) ts, close, source
                FROM ohlcv_1d
                WHERE ticker = :t
                ORDER BY ts::date,
                         CASE source WHEN 'yahoo' THEN 1
                                     WHEN 'alpaca' THEN 2
                                     WHEN 'coinbase' THEN 3
                                     ELSE 9 END
            """), {"t": tk}).all()
            if not rows:
                print(f"  {tk:<8}  (no data)")
                continue
            closes = [float(r.close) for r in rows]
            first_dt = rows[0].ts.date() if hasattr(rows[0].ts, 'date') else rows[0].ts
            last_dt = rows[-1].ts.date() if hasattr(rows[-1].ts, 'date') else rows[-1].ts
            spark = sparkline(closes, width=50)
            ret = (closes[-1] / closes[0] - 1) * 100
            # Show which source dominated (the head of the rows, oldest data)
            src = rows[0].source
            print(f"  {tk:<8}  {spark}  {first_dt}->{last_dt}  "
                  f"${closes[0]:,.0f}->${closes[-1]:,.0f}  ({ret:+.0f}%)  [{src}]")


# ─────────────────────────────────────────────────────────────────────────
# Section 3 — macro snapshot with sparklines
# ─────────────────────────────────────────────────────────────────────────
def render_macro_snapshot() -> None:
    print()
    print("=" * 78)
    print("3. MACRO SERIES — full FRED history, 50-pt sparkline")
    print("=" * 78)
    print()
    # Categorize for readability
    groups = {
        "Rates":     ["DGS2", "DGS10", "DGS30", "T10Y2Y", "T10YIE"],
        "Inflation": ["CPIAUCSL", "PCEPILFE"],
        "Labor":     ["UNRATE", "PAYEMS"],
        "Risk":      ["VIXCLS", "BAMLH0A0HYM2", "BAMLC0A0CM"],
        "FX":        ["DEXUSEU", "DEXJPUS", "DEXCHUS", "DEXKOUS"],
        "Energy":    ["DCOILWTICO", "DCOILBRENTEU", "DHHNGSP"],
        "Money/USD": ["M2SL", "WALCL", "DTWEXBGS"],
    }
    with session_scope() as s:
        for label, sids in groups.items():
            print(f"  ── {label} ──")
            for sid in sids:
                rows = s.execute(text("""
                    SELECT value FROM macro_series
                    WHERE series_id = :s ORDER BY ts
                """), {"s": sid}).all()
                if not rows:
                    print(f"    {sid:<20}  (no data)")
                    continue
                vals = [float(r.value) for r in rows]
                spark = sparkline(vals, width=50)
                latest = vals[-1]
                print(f"    {sid:<20}  {spark}  latest={latest:.2f}  n={len(vals)}")
            print()


def main() -> int:
    print()
    render_coverage()
    render_price_sparklines()
    render_macro_snapshot()
    print()
    print("Tip: extend any block in this script with your own tickers / series.")
    print("All queries use session_scope() from tessera_worker.db — same pattern")
    print("you'll use in features/compute.py for new feature columns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

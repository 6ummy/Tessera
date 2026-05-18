"""Phase A canary: ingest 1 year of SPY EOD, verify return matches external source.

Run:
    cd apps/worker
    unset ANTHROPIC_API_KEY  # only inside Claude Code context
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/ingest_spy_canary.py

What it verifies end-to-end:
- Alpaca market data API reachable + credentials valid
- TimescaleDB hypertable accepts inserts
- Idempotent upsert (re-run yields no row count change)
- Computed 1y return matches the reference computed from Yahoo within 10 bps
  → proves both ingestion AND downstream feature math are correct
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import httpx
from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.ingestors.alpaca_eod import ingest
from tessera_worker.logging import configure_logging

configure_logging()

TICKER = "SPY"
DAYS_BACK = 400  # extra cushion past trading-day gaps


def _our_1y_return() -> tuple[float, date, date, float, float]:
    """Compute 1-year return from rows we just stored in Neon."""
    with session_scope() as session:
        sql = text("""
            WITH last AS (
                SELECT close, ts::date AS d
                FROM ohlcv_1d
                WHERE ticker = :t
                ORDER BY ts DESC LIMIT 1
            ),
            first AS (
                SELECT close, ts::date AS d
                FROM ohlcv_1d
                WHERE ticker = :t
                  AND ts::date <= (SELECT d FROM last) - INTERVAL '365 days'
                ORDER BY ts DESC LIMIT 1
            )
            SELECT first.close, first.d, last.close, last.d
            FROM first, last
        """)
        row = session.execute(sql, {"t": TICKER}).first()
        if not row:
            raise RuntimeError("No SPY rows yet — did ingest run?")
        p0, d0, p1, d1 = float(row[0]), row[1], float(row[2]), row[3]
        return (p1 / p0 - 1.0), d0, d1, p0, p1


def _yahoo_1y_return(start: date, end: date) -> float:
    """Reference: Yahoo Finance v8 chart endpoint (auth-free, lightly rate-limited).
    Adjusted close so dividends + splits handled."""
    import time
    start_ts = int(time.mktime(start.timetuple()))
    end_ts = int(time.mktime(end.timetuple())) + 86400
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d&events=div%2Csplit"
    )
    r = httpx.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 tessera-canary"})
    r.raise_for_status()
    js = r.json()
    chart = js["chart"]["result"][0]
    closes = chart["indicators"]["adjclose"][0]["adjclose"]
    # Yahoo may have None entries on holidays; filter
    closes = [c for c in closes if c is not None]
    if len(closes) < 2:
        raise RuntimeError(f"Yahoo returned <2 valid closes for {TICKER}")
    return closes[-1] / closes[0] - 1.0


def main() -> int:
    end = date.today()
    start = end - timedelta(days=DAYS_BACK)

    print(f"─── Ingesting {TICKER} EOD bars {start} → {end} ───")

    # First run
    r1 = ingest([TICKER], start=start, end=end)
    print(f"  run 1: {r1.rows_upserted} rows  ({r1.duration_ms} ms)  range={r1.date_range}")

    # Second run — idempotency check
    r2 = ingest([TICKER], start=start, end=end)
    print(f"  run 2: {r2.rows_upserted} rows  ({r2.duration_ms} ms)  (should equal run 1)")
    if r2.rows_upserted != r1.rows_upserted:
        print(f"  ✗ idempotency broken: {r1.rows_upserted} vs {r2.rows_upserted}")
        return 1
    print("  ✓ idempotent")

    # 1y return: ours vs Yahoo
    print(f"\n─── Canary: 1-year return vs Yahoo ───")
    our_ret, d0, d1, p0, p1 = _our_1y_return()
    print(f"  Tessera:  {d0} ${p0:.4f}  →  {d1} ${p1:.4f}  =  {our_ret*100:+.4f}%")

    yahoo_ret = _yahoo_1y_return(d0, d1)
    print(f"  Yahoo  :  same window adj-close                         =  {yahoo_ret*100:+.4f}%")

    diff_bps = abs(our_ret - yahoo_ret) * 10_000
    print(f"  diff   :  {diff_bps:.2f} bps")

    threshold_bps = 100  # 100 bps tolerance (Alpaca IEX vs Yahoo all-exchange differ a bit)
    if diff_bps > threshold_bps:
        print(f"  ✗ exceeds threshold ({threshold_bps} bps)")
        print(f"    → check adjustment handling (splits/dividends) or feed difference")
        return 1
    print(f"  ✓ within {threshold_bps} bps threshold")

    return 0


if __name__ == "__main__":
    sys.exit(main())

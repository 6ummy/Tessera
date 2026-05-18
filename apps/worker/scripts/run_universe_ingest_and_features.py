"""Phase A end-to-end: ingest universe → build features → verify.

Run:
    cd apps/worker
    unset ANTHROPIC_API_KEY  # only in Claude Code context
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        scripts/run_universe_ingest_and_features.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.features.compute import build as build_features
from tessera_worker.ingestors.alpaca_eod import ingest as ingest_alpaca
from tessera_worker.logging import configure_logging
from tessera_worker.universe import META_BY_TICKER, TICKERS

configure_logging()

DAYS_BACK = 400  # > 1y to ensure ret_1y is computable


def main() -> int:
    end = date.today()
    start = end - timedelta(days=DAYS_BACK)

    # ── Ingest equities (Alpaca handles ETFs the same way) ────────────
    print(f"─── Universe: {len(TICKERS)} tickers ───")
    print(f"─── Ingesting {start} → {end} (Alpaca EOD, IEX) ───")
    # Alpaca's request supports multi-ticker, but BRK.B uses "." which Alpaca
    # parses as 'BRK.B'. If any ticker fails the entire batch can still return
    # data for the others.
    try:
        r = ingest_alpaca(TICKERS, start=start, end=end)
        print(f"  ✓ {r.rows_upserted} rows across {len(r.tickers)} tickers "
              f"({r.duration_ms} ms)")
    except Exception as e:
        print(f"  ✗ ingest failed: {type(e).__name__}: {e}")
        return 1

    # ── Check how many tickers actually have data ────────────────────
    with session_scope() as session:
        coverage = session.execute(text("""
            SELECT ticker, COUNT(*) AS n, MIN(ts)::date AS first, MAX(ts)::date AS last
            FROM ohlcv_1d
            WHERE ticker = ANY(:t)
            GROUP BY ticker
            ORDER BY n DESC
        """), {"t": TICKERS}).all()

    print(f"\n─── OHLCV coverage ({len(coverage)}/{len(TICKERS)} tickers landed) ───")
    missing = set(TICKERS) - {row[0] for row in coverage}
    if missing:
        print(f"  ⚠ missing: {sorted(missing)}")
    # Show a few samples
    for row in coverage[:5]:
        print(f"  {row[0]:6}  {row[1]:4} rows  {row[2]} → {row[3]}")
    if len(coverage) > 5:
        print(f"  … ({len(coverage) - 5} more)")

    # ── Build features ───────────────────────────────────────────────
    print(f"\n─── Building features ───")
    have_data = [row[0] for row in coverage]
    fr = build_features(have_data)
    print(f"  ✓ {fr.rows_written} feature rows  ({fr.duration_ms} ms)  range={fr.date_range}")

    # ── Sanity sweep: features for the most recent date per ticker ──
    print(f"\n─── Latest features (a few samples) ───")
    with session_scope() as session:
        sample = session.execute(text("""
            WITH latest AS (
                SELECT DISTINCT ON (ticker)
                       ticker, ts::date AS d,
                       ret_30d, ret_1y, vol_30d, rsi_14
                FROM ticker_features
                WHERE ticker = ANY(:t)
                ORDER BY ticker, ts DESC
            )
            SELECT * FROM latest ORDER BY ret_1y DESC NULLS LAST LIMIT 5
        """), {"t": have_data}).all()

    print(f"  Top 5 by 1y return:")
    for row in sample:
        ticker, d, r30, r1y, vol, rsi_v = row
        name = META_BY_TICKER.get(ticker)
        name_str = f" — {name.name}" if name else ""
        r30_s = f"{float(r30)*100:+.2f}%" if r30 is not None else "    n/a"
        r1y_s = f"{float(r1y)*100:+.2f}%" if r1y is not None else "    n/a"
        vol_s = f"{float(vol)*100:.1f}%" if vol is not None else " n/a"
        rsi_s = f"{float(rsi_v):.1f}" if rsi_v is not None else "n/a"
        print(f"    {ticker:6} {d}  ret_30d={r30_s}  ret_1y={r1y_s}  vol={vol_s}  rsi={rsi_s}{name_str}")

    # ── Idempotency check on features ────────────────────────────────
    print(f"\n─── Idempotency (re-build features) ───")
    fr2 = build_features(have_data)
    if fr2.rows_written == fr.rows_written:
        print(f"  ✓ same row count: {fr2.rows_written}")
    else:
        print(f"  ⚠ row count drifted: {fr.rows_written} → {fr2.rows_written}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

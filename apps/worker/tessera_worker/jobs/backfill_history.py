"""Phase C: maximum-history backfill.

One-shot operator script that pushes every source back to the earliest
date each provider supports — Alpaca to ~2018, Coinbase to 2014, FRED to
each series' inception, and (optionally) Yahoo Finance for >7yr equity
history that Alpaca's free tier can't cover.

NOT for the nightly cron. Run once when bootstrapping the backtest
harness (Phase C Week 5). Idempotent — `ON CONFLICT DO UPDATE` everywhere.

Usage:
    python -m tessera_worker.jobs.backfill_history --source alpaca
    python -m tessera_worker.jobs.backfill_history --source coinbase
    python -m tessera_worker.jobs.backfill_history --source fred
    python -m tessera_worker.jobs.backfill_history --source yahoo --years 20
    python -m tessera_worker.jobs.backfill_history --source all

Wall-clock per source (full universe):
    alpaca   ~5 min   (~70K rows over ~7 yrs × 42 equities)
    coinbase ~3 min   (~7K rows for BTC+ETH over 10+ yrs)
    fred     ~3 min   (37 series × full history each)
    yahoo    ~5 min   (rate-throttled by Yahoo)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from tessera_worker.ingestors import alpaca_eod, coinbase_eod, fred_macro
from tessera_worker.logging import configure_logging, get_logger
from tessera_worker.observability import init_sentry
from tessera_worker.universe import TICKERS, by_asset_class

configure_logging()
log = get_logger(__name__)


def backfill_alpaca(years: int = 7) -> None:
    """Pull Alpaca EOD for the equity universe going back N years.

    Alpaca free tier nominally allows up to 7 yrs (IEX feed only).
    Chunked internally so we don't hit the per-request bar cap.
    """
    end = date.today()
    start = end - timedelta(days=365 * years + 30)
    log.info("backfill.alpaca.start", start=str(start), end=str(end),
             n_tickers=len(TICKERS))
    r = alpaca_eod.ingest(TICKERS, start=start, end=end)
    log.info("backfill.alpaca.done", rows=r.rows_upserted,
             tickers=len(r.tickers), ms=r.duration_ms)


def backfill_coinbase(start_year: int = 2014) -> None:
    """Pull every daily candle Coinbase has for BTC and ETH."""
    start = date(start_year, 1, 1)
    end = date.today()
    log.info("backfill.coinbase.start", start=str(start), end=str(end))
    r = coinbase_eod.ingest(start=start, end=end)
    log.info("backfill.coinbase.done", rows=r.rows_upserted,
             pairs=len(r.pairs), ms=r.duration_ms)


def backfill_fred() -> None:
    """Pull each FRED series from its individual earliest date.

    The ingestor's `_fetch_series(start=None)` already returns full history
    when no `observation_start` is passed, so we just call ingest with
    `start=None` and let FRED return everything (UNRATE goes to 1948,
    T10YIE to 2003, recent series to their inception).
    """
    log.info("backfill.fred.start")
    r = fred_macro.ingest(start=None)  # full history
    log.info("backfill.fred.done", rows=r.rows_upserted,
             series=r.series_pulled, ms=r.duration_ms)


def backfill_yahoo(years: int = 20) -> None:
    """Optional supplement: pull yfinance for ~25yr depth per ticker.

    yfinance is an UNOFFICIAL Yahoo Finance scraper. Acceptable only for
    one-time backfill — never wire into daily cron. Rows are tagged with
    `source='yahoo'` so they don't get confused with Alpaca's IEX data.
    """
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        log.error("backfill.yahoo.missing_dep",
                  hint="pip install yfinance")
        sys.exit(2)

    from sqlalchemy import text

    from tessera_worker.db import session_scope

    tickers = [t.ticker for t in by_asset_class("equity")]
    end = date.today()
    start = end - timedelta(days=365 * years + 30)
    log.info("backfill.yahoo.start", start=str(start), end=str(end),
             n_tickers=len(tickers))

    sql = text("""
        INSERT INTO ohlcv_1d (ticker, ts, open, high, low, close, volume, vwap, source)
        VALUES (:ticker, :ts, :o, :h, :l, :c, :v, :vw, 'yahoo')
        ON CONFLICT (ticker, ts) DO UPDATE SET
            open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
            close=EXCLUDED.close, volume=EXCLUDED.volume, vwap=EXCLUDED.vwap,
            source=EXCLUDED.source
    """)
    total = 0
    for tk in tickers:
        try:
            df = yf.Ticker(tk).history(start=start.isoformat(),
                                       end=end.isoformat(), interval="1d",
                                       auto_adjust=False)
        except Exception as e:
            log.warning("backfill.yahoo.ticker_failed", ticker=tk, err=str(e))
            continue
        if df is None or df.empty:
            log.warning("backfill.yahoo.ticker_empty", ticker=tk)
            continue
        # Skip calendar days another source already covers. ohlcv_1d's PK is
        # (ticker, ts) and Yahoo stamps 00:00Z where Alpaca stamps 04:00Z, so
        # without this filter the same trading day lands twice under two ts
        # values — which silently halves the row-window horizons in
        # features/compute.py. Migration 006 cleaned the historical
        # duplicates; this keeps the backfill from re-creating them.
        with session_scope() as session:
            covered = {
                r[0] for r in session.execute(text("""
                    SELECT DISTINCT ts::date FROM ohlcv_1d
                    WHERE ticker = :t AND source <> 'yahoo'
                """), {"t": tk}).all()
            }
        rows = [
            {
                "ticker": tk,
                "ts": idx.date() if hasattr(idx, "date") else idx,
                "o": float(row["Open"]),
                "h": float(row["High"]),
                "l": float(row["Low"]),
                "c": float(row["Close"]),
                "v": int(row["Volume"]) if row["Volume"] else 0,
                "vw": None,  # Yahoo doesn't expose VWAP
            }
            for idx, row in df.iterrows()
            if not any(x is None or x != x
                       for x in (row["Open"], row["High"], row["Low"], row["Close"]))
            and (idx.date() if hasattr(idx, "date") else idx) not in covered
        ]
        if not rows:
            continue
        with session_scope() as session:
            session.execute(sql, rows)
        total += len(rows)
        log.info("backfill.yahoo.ticker_done", ticker=tk, rows=len(rows))

    log.info("backfill.yahoo.done", rows=total, tickers=len(tickers))


def main(argv: list[str] | None = None) -> int:
    init_sentry()
    parser = argparse.ArgumentParser(description="Tessera historical backfill")
    parser.add_argument(
        "--source",
        choices=("alpaca", "coinbase", "fred", "yahoo", "all"),
        required=True,
        help="Which data source to backfill",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=7,
        help="Years of history (default: alpaca=7, yahoo=20)",
    )
    args = parser.parse_args(argv)

    if args.source in ("alpaca", "all"):
        backfill_alpaca(years=args.years if args.years != 7 else 7)
    if args.source in ("coinbase", "all"):
        backfill_coinbase()
    if args.source in ("fred", "all"):
        backfill_fred()
    if args.source == "yahoo":
        backfill_yahoo(years=args.years if args.years > 7 else 20)
    elif args.source == "all":
        log.info("backfill.skipping_yahoo",
                 reason="opt-in only: rerun with --source yahoo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

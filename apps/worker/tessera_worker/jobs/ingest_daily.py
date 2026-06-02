"""Daily ingestion orchestrator — what Vercel Cron triggers.

Sequence (each step idempotent, independently retriable):
1. Alpaca EOD (equities + ETFs)
2. Coinbase EOD (BTC, ETH)
3. FRED macro
4. FMP fundamentals (only refresh if last update > 30 days; quarterly cadence)
5. NewsAPI news (last 24h)
6. Feature builder (recompute ticker_features for the full universe)

Run:
    python -m tessera_worker.jobs.ingest_daily
    python -m tessera_worker.jobs.ingest_daily --skip fundamentals
    python -m tessera_worker.jobs.ingest_daily --only ohlcv features

Exit code 0 if all requested steps succeeded; 1 if any failed.
Cloud Run Jobs maps exit-code-nonzero to "Failed" state for alerting.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.features.compute import build as build_features
from tessera_worker.ingestors import (
    alpaca_eod,
    coinbase_eod,
    fmp_fundamentals,
    fred_macro,
    newsapi_news,
    sec_edgar,
    sec_edgar_facts,
)
from tessera_worker.logging import configure_logging, get_logger
from tessera_worker.universe import TICKERS, by_asset_class

configure_logging()
log = get_logger(__name__)


@dataclass
class StepResult:
    name: str
    ok: bool
    duration_ms: int
    details: dict[str, object] = field(default_factory=dict)
    error: str | None = None


# Step name → (when_to_run_check, runner). Names are how --only / --skip refer to them.
StepFn = Callable[[], dict[str, object]]


def _step_ohlcv_equity() -> dict[str, object]:
    """Pull last ~30 days for the equity universe. Idempotent, so even on
    weekends/holidays the call is safe — it just upserts the same rows."""
    end = date.today()
    start = end - timedelta(days=30)
    r = alpaca_eod.ingest(TICKERS, start=start, end=end)
    return {"rows": r.rows_upserted, "tickers": len(r.tickers), "ms": r.duration_ms}


def _step_ohlcv_crypto() -> dict[str, object]:
    end = date.today()
    start = end - timedelta(days=30)
    r = coinbase_eod.ingest(start=start, end=end)
    return {"rows": r.rows_upserted, "pairs": len(r.pairs), "ms": r.duration_ms}


def _step_macro() -> dict[str, object]:
    """Pull last 90 days of macro series (cheap, covers any late revisions)."""
    r = fred_macro.ingest(start=date.today() - timedelta(days=90))
    return {"rows": r.rows_upserted, "series": r.series_pulled, "ms": r.duration_ms}


def _step_fundamentals() -> dict[str, object]:
    """Pull annual fundamentals only if our newest row is older than 30 days
    for that ticker. Avoids burning the FMP quota daily on data that updates
    quarterly."""
    tickers = [t.ticker for t in by_asset_class("equity")]
    # Get freshness from DB in one query, compute "stale" set in Python.
    # (Doing the comparison in SQL with `unnest(:tickers::text[])` collides with
    # psycopg's param marker — `::` is both a cast and the marker delimiter.)
    with session_scope() as session:
        rows = session.execute(text("""
            SELECT ticker, MAX(fetched_at) AS last_fetch
            FROM fundamentals
            WHERE ticker = ANY(:tickers)
            GROUP BY ticker
        """), {"tickers": tickers}).all()
    from datetime import timezone as _tz
    fresh: set[str] = set()
    cutoff = datetime.now(_tz.utc) - timedelta(days=30)
    for ticker, last_fetch in rows:
        if last_fetch and last_fetch > cutoff:
            fresh.add(ticker)
    stale = [t for t in tickers if t not in fresh]
    if not stale:
        return {"rows_upserted": 0, "n_tickers": 0, "skipped_reason": "all_fresh"}
    r = fmp_fundamentals.ingest(tickers=stale, period="annual", limit=5)
    return {"rows_upserted": r.rows_upserted, "n_tickers": len(r.tickers)}


def _step_news() -> dict[str, object]:
    r = newsapi_news.ingest(since=date.today() - timedelta(days=1))
    return {"rows": r.rows_upserted, "tickers": r.tickers_queried, "ms": r.duration_ms}


def _step_filings() -> dict[str, object]:
    """Pull recent 10-K/10-Q filings for the equity universe.

    Filings are quarterly cadence at most; the ingestor skips any accession we
    already have a non-empty text_summary for, so daily runs are mostly no-ops
    once steady-state. First populated run will be heavier (~50 filings).
    """
    tickers = [t.ticker for t in by_asset_class("equity")]
    r = sec_edgar.ingest(tickers)
    return {
        "filings": r.filings_upserted,
        "bytes_uploaded": r.bytes_uploaded,
        "missing_cik": len(r.tickers_missing_cik),
        "ms": r.duration_ms,
    }


def _step_edgar_facts() -> dict[str, object]:
    """Pull SEC XBRL companyfacts (structured GAAP fundamentals).

    Covers tickers FMP free tier blocks (HON, LLY, MA, etc.). Daily runs are
    mostly no-ops once steady-state because companyfacts only updates when a
    new 10-K/10-Q is filed; the JSONB-merge upsert pattern means re-fetching
    the same period_end is harmless. ~30s for full universe.
    """
    tickers = [t.ticker for t in by_asset_class("equity")]
    r = sec_edgar_facts.ingest(tickers)
    return {
        "rows": r.rows_upserted,
        "tickers": r.tickers_processed,
        "missing_cik": len(r.tickers_missing_cik),
        "no_data": len(r.tickers_no_data),
        "ms": r.duration_ms,
    }


def _step_features() -> dict[str, object]:
    """Recompute features for everything that has OHLCV. Idempotent."""
    with session_scope() as session:
        tickers = [r[0] for r in session.execute(
            text("SELECT DISTINCT ticker FROM ohlcv_1d")
        ).all()]
    r = build_features(tickers)
    return {"rows": r.rows_written, "tickers": len(r.tickers), "ms": r.duration_ms}


STEPS: dict[str, StepFn] = {
    "ohlcv_equity":  _step_ohlcv_equity,
    "ohlcv_crypto":  _step_ohlcv_crypto,
    "macro":         _step_macro,
    "fundamentals":  _step_fundamentals,    # FMP — limited free-tier coverage
    "edgar_facts":   _step_edgar_facts,     # SEC XBRL — fills FMP gaps via JSONB merge
    "news":          _step_news,
    "filings":       _step_filings,         # SEC 10-K/10-Q text → GCS
    "features":      _step_features,
}


def run(only: list[str] | None = None, skip: list[str] | None = None) -> list[StepResult]:
    """Execute the daily pipeline. Skip-list applied after only-list."""
    only_set = set(only or STEPS.keys())
    skip_set = set(skip or [])
    plan = [name for name in STEPS if name in only_set and name not in skip_set]

    log.info("ingest_daily.start", steps=plan)
    results: list[StepResult] = []
    for name in plan:
        started = datetime.now()
        try:
            details = STEPS[name]()
            ok = True
            err = None
        except Exception as e:
            ok = False
            err = f"{type(e).__name__}: {e}"
            details = {}
            log.error("ingest_daily.step_failed", step=name, err=err,
                      tb=traceback.format_exc()[:2000])
        duration_ms = int((datetime.now() - started).total_seconds() * 1000)
        results.append(StepResult(name=name, ok=ok, duration_ms=duration_ms,
                                  details=details, error=err))
        # Merge details into a single dict so kwargs can't collide with `ms` etc.
        # If a step's details dict carries an `ms` field, it overrides the outer one.
        log_kwargs: dict[str, object] = {"step": name, "ok": ok, "duration_ms": duration_ms}
        if ok:
            log_kwargs.update(details)
        log.info("ingest_daily.step_done", **log_kwargs)

    log.info("ingest_daily.summary",
             total_ms=sum(r.duration_ms for r in results),
             passed=sum(r.ok for r in results),
             failed=sum(not r.ok for r in results))
    return results


def main(argv: list[str] | None = None) -> int:
    # CLI entry — init Sentry here too (FastAPI path inits in main.py).
    from tessera_worker.observability import init_sentry
    init_sentry()

    parser = argparse.ArgumentParser(description="Tessera daily ingest")
    parser.add_argument("--only", nargs="+", choices=list(STEPS),
                        help="Run only these steps (default: all)")
    parser.add_argument("--skip", nargs="+", choices=list(STEPS), default=[],
                        help="Skip these steps")
    args = parser.parse_args(argv)

    results = run(only=args.only, skip=args.skip)

    # Console summary (always — Cloud Run captures stdout for logs).
    # Use ASCII only — Windows cp1252 consoles can't encode box-drawing chars.
    print()
    print("--- ingest_daily summary ---")
    for r in results:
        flag = "OK " if r.ok else "ERR"
        det = " ".join(f"{k}={v}" for k, v in r.details.items()) if r.ok else r.error
        print(f"  [{flag}] {r.name:14}  {r.duration_ms:>6} ms  {det}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

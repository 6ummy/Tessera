"""Daily ingestion orchestrator — what Vercel Cron triggers.

Steps run in STEPS-dict order, each idempotent and independently retriable:
ohlcv (Alpaca equities + Coinbase crypto) → FRED macro → fundamentals
(FMP 30-day cache → SEC XBRL → FMP key-metrics → yfinance shares daily /
history weekly) → news → SEC filings → feature builder → coverage audit →
SPY canary (read-only; >100bps divergence vs Yahoo fails the run).

The whole run holds a Postgres advisory lock — a second trigger landing
mid-run returns immediately as a no-op.

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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from tessera_worker.db import session_scope, try_advisory_lock
from tessera_worker.features.compute import build as build_features
from tessera_worker.ingestors import (
    alpaca_eod,
    coinbase_eod,
    fmp_fundamentals,
    fmp_key_metrics,
    fred_macro,
    newsapi_news,
    sec_edgar,
    sec_edgar_facts,
    yf_history,
    yf_shares,
)
from tessera_worker.logging import configure_logging, get_logger
from tessera_worker.universe import by_asset_class

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
    """Pull last ~30 days for the equity + ETF universe. Idempotent, so
    even on weekends/holidays the call is safe — it just upserts the same
    rows.

    Equities + ETFs ONLY — crypto pairs go through _step_ohlcv_crypto
    (Coinbase). Alpaca's stock feed rejects a crypto symbol (e.g.
    AVAX/USD) and fails the ENTIRE batch request, not just that symbol.
    Before the crypto universe expansion (2026-06-09) `TICKERS` was
    all-equity and this passed it directly; after, one crypto pair broke
    the whole equity pull. The Service path swallowed the non-zero exit,
    so equity OHLCV silently froze for ~9 days until the Cloud Run Job
    surfaced exit code 1 (CS-12)."""
    end = date.today()
    start = end - timedelta(days=30)
    tickers = [t.ticker for t in by_asset_class("equity")]
    tickers += [t.ticker for t in by_asset_class("etf")]
    r = alpaca_eod.ingest(tickers, start=start, end=end)
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
    fresh: set[str] = set()
    cutoff = datetime.now(UTC) - timedelta(days=30)
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


def _step_fmp_key_metrics() -> dict[str, object]:
    """Pull TTM key metrics (current marketCap + freeCashFlowYieldTTM +
    PE/ROE/etc) from FMP. Adds a 5th candidate to estimate_market_cap()
    and gives compute.py a cross-check for its own fcf_yield computation.

    Cheap call (1 request per ticker, ~50 requests for the equity
    universe). Daily refresh is appropriate — marketCap shifts with
    close, and FMP recomputes the TTM ratios daily too."""
    tickers = [t.ticker for t in by_asset_class("equity")]
    r = fmp_key_metrics.ingest(tickers)
    return {
        "rows": r.rows_upserted,
        "tickers": r.tickers_processed,
        "no_data": len(r.tickers_no_data),
        "ms": r.duration_ms,
    }


def _step_yf_shares() -> dict[str, object]:
    """Pull sharesOutstanding + marketCap from yfinance for the equity
    universe. Used as a last-resort fill for tickers whose XBRL + FMP
    rows leave share counts blank (V is the canonical case)."""
    tickers = [t.ticker for t in by_asset_class("equity")]
    r = yf_shares.ingest(tickers)
    return {
        "rows": r.rows_upserted,
        "tickers": r.tickers_processed,
        "no_data": len(r.tickers_no_data),
        "ms": r.duration_ms,
    }


def _step_yf_history() -> dict[str, object]:
    """Weekly: pull annual income-statement history from yfinance for
    the equity universe. Idempotent — JSONB merge so daily-pass values
    (FMP / EDGAR) keep priority on overlapping keys; yf fills only the
    NULL slots downstream computations need (eps_cagr_3y,
    gross_margin_trend).

    Cadence guard: only runs on Friday (weekday() == 4). yfinance's
    income_stmt endpoint is slow + aggressively throttled, and annual
    statements only refresh quarterly — daily would be wasteful and risk
    Yahoo blocking. Manual invocation always runs regardless of day."""
    if date.today().weekday() != 4:
        return {"rows": 0, "tickers": 0, "skipped_reason": "non_friday"}
    tickers = [t.ticker for t in by_asset_class("equity")]
    r = yf_history.ingest(tickers)
    return {
        "rows": r.rows_upserted,
        "tickers": r.tickers_processed,
        "no_data": len(r.tickers_no_data),
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


def _step_coverage_audit() -> dict[str, object]:
    """Log tickers whose latest ticker_features row has a NULL in any of
    the four "must-have" UI columns: fcf_yield, market_cap_usd, peg,
    gross_margin. ETFs and crypto are excluded — they don't carry
    fundamentals by design.

    This step is read-only — purely for Grafana / Sentry to scrape the
    structured log line and alert when coverage degrades. A new universe
    addition that hits this audit on its first cron is the canonical
    moment to add a yfinance / EDGAR mapping for the gap.
    """
    equity_tickers = {t.ticker for t in by_asset_class("equity")}
    if not equity_tickers:
        return {"equity_tickers": 0, "with_gaps": 0}
    with session_scope() as session:
        rows = session.execute(text("""
            SELECT DISTINCT ON (ticker)
                   ticker,
                   fcf_yield IS NULL      AS gap_fcf_yield,
                   market_cap_usd IS NULL AS gap_market_cap,
                   peg IS NULL            AS gap_peg,
                   gross_margin IS NULL   AS gap_gross_margin
            FROM ticker_features
            WHERE ticker = ANY(:t)
            ORDER BY ticker, ts DESC
        """), {"t": list(equity_tickers)}).all()
    gaps: dict[str, list[str]] = {}
    for r in rows:
        miss = []
        if r.gap_fcf_yield:
            miss.append("fcf_yield")
        if r.gap_market_cap:
            miss.append("market_cap_usd")
        if r.gap_peg:
            miss.append("peg")
        if r.gap_gross_margin:
            miss.append("gross_margin")
        if miss:
            gaps[r.ticker] = miss
    if gaps:
        # Structured log — one log line per gap-ticker for easy scrape.
        for tk, miss in gaps.items():
            log.warning("features.coverage_gap", ticker=tk, missing=miss)
    return {
        "equity_tickers": len(equity_tickers),
        "with_gaps":      len(gaps),
        "gap_tickers":    sorted(gaps.keys()),
    }


def _step_spy_canary() -> dict[str, object]:
    """Read-only: SPY 1y return from our rows vs Yahoo reference.

    Beyond-threshold divergence raises → step fails → exit 1 / Sentry.
    Yahoo being unreachable is logged + skipped (their outage, not our
    regression). See jobs/spy_canary.py for why this is a nightly step.
    """
    import httpx as _httpx

    from tessera_worker.jobs.spy_canary import run_canary

    try:
        r = run_canary()
    except (_httpx.HTTPError, KeyError, IndexError) as e:
        log.warning("spy_canary.reference_unavailable", err=str(e))
        return {"skipped_reason": f"yahoo_unavailable: {type(e).__name__}"}
    return {
        "diff_bps": round(r.diff_bps, 2),
        "our_return": round(r.our_return, 6),
        "yahoo_return": round(r.yahoo_return, 6),
        "window": f"{r.window_start}->{r.window_end}",
    }


def _step_paper_engine() -> dict[str, object]:
    """Paper execution: fill the latest unexecuted book at today's open,
    mark-to-market at today's close, write persona_performance.

    Gated on FEATURE_PAPER_EXECUTION so the code can ship dark and the
    operator flips the flag after verifying a dry week of logs. Runs
    LAST — it needs today's bars (ohlcv steps) and benefits from the
    canary having vouched for them.
    """
    from tessera_worker.config import get_settings

    if not get_settings().feature_paper_execution:
        return {"skipped_reason": "FEATURE_PAPER_EXECUTION=false"}
    from tessera_worker.risk.paper_engine import run_paper_engine

    return run_paper_engine()


STEPS: dict[str, StepFn] = {
    "ohlcv_equity":  _step_ohlcv_equity,
    "ohlcv_crypto":  _step_ohlcv_crypto,
    "macro":         _step_macro,
    "fundamentals":  _step_fundamentals,    # FMP — limited free-tier coverage
    "edgar_facts":   _step_edgar_facts,     # SEC XBRL — fills FMP gaps via JSONB merge
    "fmp_key_metrics": _step_fmp_key_metrics, # FMP TTM mcap/ratios — daily 5th mcap candidate
    "yf_shares":     _step_yf_shares,       # yfinance — last-resort shares + mcap
    "yf_history":    _step_yf_history,      # yfinance — weekly annual income history
    "news":          _step_news,
    "filings":       _step_filings,         # SEC 10-K/10-Q text → GCS
    "features":      _step_features,
    "coverage":      _step_coverage_audit,  # post-build NULL audit per ticker
    "canary":        _step_spy_canary,      # SPY 1y return vs Yahoo, >100bps fails
    "paper":         _step_paper_engine,    # fills + MTM + performance (flag-gated)
}


def run(only: list[str] | None = None, skip: list[str] | None = None) -> list[StepResult]:
    """Execute the daily pipeline. Skip-list applied after only-list.

    Guarded by a Postgres advisory lock: if a second trigger lands while a
    run is in flight (manual curl + scheduled cron in the same window), the
    second returns immediately as a no-op instead of running the pipeline
    in parallel. Steps are idempotent so parallel runs were never
    *corrupting*, but they doubled third-party API usage and produced
    confusing interleaved step_failed logs (architecture.md concurrent-run
    note, resolved 2026-06-11).
    """
    with try_advisory_lock("ingest_daily") as acquired:
        if not acquired:
            log.warning("ingest_daily.skipped_already_running",
                        hint="another ingest_daily holds the advisory lock")
            return [StepResult(
                name="advisory_lock", ok=True, duration_ms=0,
                details={"skipped_reason": "another run holds the lock"},
            )]
        return _run_locked(only=only, skip=skip)


def _run_locked(only: list[str] | None, skip: list[str] | None) -> list[StepResult]:
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

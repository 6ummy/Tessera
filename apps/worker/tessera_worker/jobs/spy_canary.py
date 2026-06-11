"""SPY 1-year-return canary — automated guard on the price/feature plane.

Compares the 1y SPY return computed from our `ohlcv_1d` rows against the
same window computed from Yahoo Finance's chart endpoint. A divergence
beyond THRESHOLD_BPS means OUR data (or the math reading it) drifted —
exactly the class of regression the 2026-06-11 P0-1 incident showed can
sit undetected: duplicate calendar-day rows distorted every row-window
feature for weeks, and the canary that would have caught it only existed
as a manual operator script (`scripts/ingest_spy_canary.py`).

This module is the same comparison wired into the daily orchestrator as a
read-only step (after `features`):
  - diff within threshold  → step ok, diff logged for trend-watching.
  - diff beyond threshold  → RuntimeError → ingest_daily.step_failed →
    CLI exit 1 / Sentry. Stop-the-world signal: do not trust features
    until an operator looks.
  - Yahoo unreachable      → step ok with skipped_reason. The canary
    guards OUR math; a Yahoo outage is not our regression and must not
    fail the nightly pipeline.

The manual script remains for ad-hoc verification (it additionally tests
Alpaca ingestion idempotency, which doesn't belong in the nightly path).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

import httpx
from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

TICKER = "SPY"
THRESHOLD_BPS = 100.0  # Alpaca IEX vs Yahoo all-exchange differ a little


@dataclass(frozen=True, slots=True)
class CanaryResult:
    ticker: str
    our_return: float
    yahoo_return: float
    diff_bps: float
    window_start: date
    window_end: date


def _our_1y_return() -> tuple[float, date, date]:
    """1-year return from our stored rows: latest close vs the newest close
    at least 365 days older. Same query as scripts/ingest_spy_canary.py."""
    with session_scope() as session:
        row = session.execute(text("""
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
        """), {"t": TICKER}).first()
    if not row:
        raise RuntimeError(f"no {TICKER} rows in ohlcv_1d — canary cannot run")
    p0, d0, p1, d1 = float(row[0]), row[1], float(row[2]), row[3]
    return (p1 / p0 - 1.0), d0, d1


def _yahoo_1y_return(start: date, end: date) -> float:
    """Reference return over the same window from Yahoo's chart endpoint
    (auth-free). Raises on any transport/shape problem — the caller maps
    that to a skip, not a failure."""
    start_ts = int(time.mktime(start.timetuple()))
    end_ts = int(time.mktime(end.timetuple())) + 86400
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d&events=div%2Csplit"
    )
    r = httpx.get(url, timeout=15,
                  headers={"User-Agent": "Mozilla/5.0 tessera-canary"})
    r.raise_for_status()
    chart = r.json()["chart"]["result"][0]
    closes = [float(c) for c in chart["indicators"]["adjclose"][0]["adjclose"]
              if c is not None]
    if len(closes) < 2:
        raise RuntimeError(f"Yahoo returned <2 valid closes for {TICKER}")
    return closes[-1] / closes[0] - 1.0


def run_canary() -> CanaryResult:
    """Compute both returns and return the comparison. Raises RuntimeError
    when the divergence exceeds THRESHOLD_BPS."""
    our_ret, d0, d1 = _our_1y_return()
    yahoo_ret = _yahoo_1y_return(d0, d1)
    diff_bps = abs(our_ret - yahoo_ret) * 10_000
    result = CanaryResult(
        ticker=TICKER, our_return=our_ret, yahoo_return=yahoo_ret,
        diff_bps=diff_bps, window_start=d0, window_end=d1,
    )
    if diff_bps > THRESHOLD_BPS:
        log.error("spy_canary.FAILED",
                  our_return=round(our_ret, 6),
                  yahoo_return=round(yahoo_ret, 6),
                  diff_bps=round(diff_bps, 2),
                  threshold_bps=THRESHOLD_BPS)
        raise RuntimeError(
            f"SPY 1y return diverges from Yahoo by {diff_bps:.2f} bps "
            f"(threshold {THRESHOLD_BPS:.0f}) — ours {our_ret:+.4%} vs "
            f"Yahoo {yahoo_ret:+.4%} over {d0} → {d1}. Do not trust "
            f"ticker_features until investigated."
        )
    log.info("spy_canary.ok", diff_bps=round(diff_bps, 2),
             our_return=round(our_ret, 6), yahoo_return=round(yahoo_ret, 6))
    return result

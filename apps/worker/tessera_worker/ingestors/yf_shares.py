"""yfinance shares-outstanding fallback ingestor.

Last-resort source for shares outstanding + market cap, used when both
FMP and SEC EDGAR companyfacts come up dry. The canonical case is V
(Visa): post-2010 Visa stopped tagging EntityCommonStockSharesOutstanding
in its XBRL filings and never tags WeightedAverageNumberOfShares* under
us-gaap at all, so our regular fundamentals path leaves shares NULL and
fcf_yield / market_cap_usd unreachable downstream.

yfinance is an unofficial Yahoo Finance scraper (no SLA, undocumented
shape changes possible), which is why it's a *fallback* and not the
primary path — but for a slow-moving number like sharesOutstanding it's
reliable enough for our weekly persona batch. Already a pyproject dep
for the long-horizon backfill job.

Storage: writes to the existing `fundamentals` table as a synthetic
income row keyed `(ticker, today, 'income')`. Loader code already walks
newest-first per field, so today's row supplies the share count without
touching schema. EDGAR / FMP rows with real quarterly period_end still
exist and remain the source for everything else (revenue, OCF, debt, …).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    tickers_processed: int
    rows_upserted: int
    tickers_no_data: list[str] = field(default_factory=list)
    duration_ms: int = 0


def _fetch_one(ticker: str) -> dict | None:
    """Return {sharesOutstanding, marketCap} from yfinance, or None on failure.

    yfinance's `Ticker.info` is the property that hits Yahoo's quote-summary
    endpoint; it's the most reliable single call for static company data.
    Wrapped in a broad try/except because yfinance routinely raises on
    transient HTTP issues and we'd rather skip a name than abort the batch.
    """
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        log.error("yf_shares.yfinance_not_installed",
                  hint="pip install yfinance")
        return None
    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        log.warning("yf_shares.fetch_failed", ticker=ticker, err=str(e))
        return None
    shares = info.get("sharesOutstanding")
    mcap = info.get("marketCap")
    if shares is None and mcap is None:
        return None
    return {
        "sharesOutstanding": shares,
        "marketCap":         mcap,
    }


def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    # JSONB-merge so a re-run today refreshes shares without dropping any
    # other field that might have been attached to today's synthetic row.
    # filing_type='income' chosen so compute.py's _load_fundamentals_latest
    # picks the shares up via its existing income-rows walk — no compute
    # change required.
    sql = text("""
        INSERT INTO fundamentals (ticker, period_end, filing_type, payload)
        VALUES (:ticker, :period_end, :filing_type, CAST(:payload AS JSONB))
        ON CONFLICT (ticker, period_end, filing_type)
        DO UPDATE SET
            payload = fundamentals.payload || EXCLUDED.payload,
            fetched_at = NOW()
    """)
    written = 0
    with session_scope() as session:
        for r in rows:
            session.execute(sql, r)
            written += 1
    return written


def ingest(tickers: Iterable[str]) -> IngestResult:
    """Pull sharesOutstanding + marketCap from yfinance for each ticker.

    Skips tickers where yfinance returns no usable data. Writes a single
    synthetic income row per ticker keyed on today's date.
    """
    tickers_list = sorted({t.upper() for t in tickers})
    started = datetime.now()
    log.info("yf_shares.start", n_tickers=len(tickers_list))

    today = date.today()
    rows: list[dict] = []
    no_data: list[str] = []

    for tk in tickers_list:
        data = _fetch_one(tk)
        if not data:
            no_data.append(tk)
            continue
        shares = data.get("sharesOutstanding")
        mcap = data.get("marketCap")
        payload = {
            "source":                    "yfinance",
            "weightedAverageShsOut":     shares,
            "weightedAverageShsOutDil":  shares,  # yf doesn't split diluted
            "marketCap":                 mcap,
        }
        rows.append({
            "ticker":      tk,
            "period_end":  today,
            "filing_type": "income",
            "payload":     json.dumps(payload),
        })

    written = _upsert(rows)
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="yf_shares",
        tickers_processed=len(tickers_list),
        rows_upserted=written,
        tickers_no_data=no_data,
        duration_ms=duration_ms,
    )
    log.info("yf_shares.done",
             tickers=len(tickers_list),
             rows=written,
             no_data=len(no_data),
             ms=duration_ms)
    return result

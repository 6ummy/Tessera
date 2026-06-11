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


def _to_yahoo_symbol(ticker: str) -> str:
    """Map our universe ticker to Yahoo Finance's symbol convention.

    Yahoo uses `-` as the class separator (BRK-B, BF-B) where SEC / Alpaca
    / our universe use `.` (BRK.B). Without the swap yfinance returns
    empty info for these dual-class names.
    """
    return ticker.replace(".", "-")


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
    yahoo_symbol = _to_yahoo_symbol(ticker)
    try:
        info = yf.Ticker(yahoo_symbol).info
    except Exception as e:
        log.warning("yf_shares.fetch_failed", ticker=ticker,
                    yahoo_symbol=yahoo_symbol, err=str(e))
        return None
    shares = info.get("sharesOutstanding")
    mcap = info.get("marketCap")
    # Yahoo-derived ratios for tickers whose XBRL doesn't expose the
    # inputs we need: peg (V has no historical EPS in us-gaap) and gross
    # margin (V doesn't tag GrossProfit at all). compute.py uses these
    # only as fallback when its own EDGAR-derived computation returns None.
    # Yahoo's grossMargins for service businesses uses a non-GAAP-friendly
    # definition (V ≈ 97% — basically revenue minus client incentives);
    # acceptable for the "valuation at a glance" UI, less so for rigorous
    # cross-ticker quality comparison.
    peg = info.get("trailingPegRatio") or info.get("pegRatio")
    gross_margins = info.get("grossMargins")
    # P/E: prefer trailing (12-month actual) over forward (12-month estimate)
    # since trailing matches our backwards-looking fcf_yield / margins UI.
    # Forward kept as a separate field for personas (e.g. Cathie) who may
    # want it; UI strip uses trailing by default.
    pe_trailing = info.get("trailingPE")
    pe_forward = info.get("forwardPE")
    if all(v is None for v in (shares, mcap, peg, gross_margins, pe_trailing, pe_forward)):
        return None
    return {
        "sharesOutstanding": shares,
        "marketCap":         mcap,
        "pegRatio":          peg,
        "grossMargins":      gross_margins,
        "trailingPE":        pe_trailing,
        "forwardPE":         pe_forward,
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
    # Fail loudly if yfinance isn't installed. Before 2026-06-11 the
    # ImportError was swallowed per ticker inside _fetch_one, so a prod
    # image built without the dependency reported the step as ok=True with
    # every ticker in no_data — and the 3rd fall-through tier silently
    # stopped flowing. A hard failure surfaces as ingest_daily.step_failed
    # → exit 1 → Sentry instead.
    try:
        import yfinance  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "yfinance is not installed but is a core dependency since "
            "2026-06-11 — rebuild the worker image (pip install .)"
        ) from e

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
        peg = data.get("pegRatio")
        gross_margins = data.get("grossMargins")
        # Store with the same field names compute.py will look for in its
        # yf-fallback branch. `peg_yf` / `gross_margin_yf` are dedicated
        # keys so we don't accidentally clobber an EDGAR-derived value
        # in a downstream || jsonb merge.
        payload = {
            "source":                    "yfinance",
            "weightedAverageShsOut":     shares,
            "weightedAverageShsOutDil":  shares,  # yf doesn't split diluted
            "marketCap":                 mcap,
            "peg_yf":                    peg,
            "gross_margin_yf":           gross_margins,
            "pe_trailing_yf":            data.get("trailingPE"),
            "pe_forward_yf":             data.get("forwardPE"),
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

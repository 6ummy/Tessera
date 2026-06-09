"""yfinance historical income-statement ingestor.

Last-resort source for **multi-year history** of EPS / revenue / grossProfit.
Used to unlock `eps_cagr_3y` + `gross_margin_trend` for tickers whose
XBRL doesn't tag the relevant us-gaap concepts (V doesn't tag
EarningsPerShareDiluted or GrossProfit at all; many service / payment
filers are in the same boat).

Why this is a separate ingestor and not part of `yf_shares.py`:
  - `yf_shares` is a fast (~15s for the universe) Ticker.info pull. Yahoo
    serves that endpoint cheaply enough to run daily.
  - `Ticker.income_stmt` is a heavier, scraped financials endpoint. It
    routinely takes 1–3s per ticker and Yahoo aggressively rate-limits at
    burst (~4 rps soft cap, opaque). Universe-wide that's 3+ min and risks
    a temporary block.
  - Income statement only refreshes once a quarter, so a *weekly* cadence
    is plenty. Wired into the weekly orchestrator, not daily.

Storage: writes one synthetic ROW PER FISCAL YEAR into `fundamentals`
table — `(ticker, fy_end_date, 'income')` payload with `epsDiluted`,
`revenue`, `grossProfit`, `period='FY'`, `source='yfinance_history'`.
`compute.py::_annual_income_rows` already filters by `period='FY'` and
walks them newest-first per field, so as soon as these rows land the
`compute_eps_cagr_3y` + `compute_gross_margin_trend` paths produce
non-None values for those tickers — zero compute changes required.

Caveat: yfinance's income_stmt returns reported (GAAP) numbers when the
filer publishes them, but Yahoo's row labeling drifts (`Basic EPS` vs
`Diluted EPS`, `Gross Profit` vs `Cost Of Revenue` derivations). We use
defensive label matching with priority lists; rows where neither EPS
candidate is present are skipped rather than zero-filled.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)


# Yahoo's income_stmt DataFrame index labels we'll accept for each
# logical field. First match wins. Yahoo periodically renames these
# between API revisions; keep the priority list small and ordered by
# what we've observed in practice.
EPS_LABELS = ("Diluted EPS", "Basic EPS", "Eps Diluted", "Eps Basic")
REVENUE_LABELS = ("Total Revenue", "Operating Revenue", "Revenue")
GROSS_PROFIT_LABELS = ("Gross Profit",)
OPERATING_INCOME_LABELS = ("Operating Income", "Operating Income/Loss")

THROTTLE_S = 0.8  # ~1.25 req/s — well under Yahoo's soft burst cap


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    tickers_processed: int
    rows_upserted: int
    tickers_no_data: list[str] = field(default_factory=list)
    duration_ms: int = 0


def _to_yahoo_symbol(ticker: str) -> str:
    """BRK.B → BRK-B; same convention as yf_shares."""
    return ticker.replace(".", "-")


def _pick_label(df, labels: tuple[str, ...]):
    """Return the row for the first matching label, or None."""
    for lbl in labels:
        if lbl in df.index:
            return df.loc[lbl]
    return None


def _safe_float(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # yfinance encodes missing periods as NaN
    if f != f:
        return None
    return f


def _fetch_one(ticker: str) -> list[dict] | None:
    """Pull 4 annual periods of income statement for one ticker.

    Returns a list of `{fy_end, epsDiluted, revenue, grossProfit,
    operatingIncome}` dicts, newest first. None on hard failure.
    """
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        log.error("yf_history.yfinance_not_installed",
                  hint="pip install yfinance")
        return None
    yahoo_symbol = _to_yahoo_symbol(ticker)
    try:
        # `.income_stmt` is the annual report; `.quarterly_income_stmt`
        # would be quarterly. Annual is enough for the 3y CAGR + trend
        # we care about, and Yahoo serves annuals more reliably.
        df = yf.Ticker(yahoo_symbol).income_stmt
    except Exception as e:
        log.warning("yf_history.fetch_failed", ticker=ticker,
                    yahoo_symbol=yahoo_symbol, err=str(e))
        return None
    if df is None or df.empty:
        return None

    eps_row = _pick_label(df, EPS_LABELS)
    revenue_row = _pick_label(df, REVENUE_LABELS)
    gross_profit_row = _pick_label(df, GROSS_PROFIT_LABELS)
    operating_income_row = _pick_label(df, OPERATING_INCOME_LABELS)

    # Columns of df are Timestamps (fiscal-year ends) in descending order.
    out: list[dict] = []
    for col in df.columns:
        try:
            fy_end = col.date() if hasattr(col, "date") else col
        except Exception:
            continue
        eps = _safe_float(eps_row[col]) if eps_row is not None else None
        revenue = _safe_float(revenue_row[col]) if revenue_row is not None else None
        gross_profit = (
            _safe_float(gross_profit_row[col]) if gross_profit_row is not None else None
        )
        operating_income = (
            _safe_float(operating_income_row[col])
            if operating_income_row is not None
            else None
        )
        # Skip a row that has nothing useful — keeping it would only waste
        # an upsert without enabling any downstream computation.
        if eps is None and revenue is None and gross_profit is None:
            continue
        out.append({
            "fy_end":          fy_end,
            "epsDiluted":      eps,
            "revenue":         revenue,
            "grossProfit":     gross_profit,
            "operatingIncome": operating_income,
        })
    return out or None


def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    # JSONB merge: if EDGAR or FMP already wrote a row for this fy_end,
    # their values win on overlapping keys (we use yf to fill gaps, not
    # override canonical sources). yfinance fills only NULL slots that
    # the canonical row didn't populate, because of the ON CONFLICT
    # merge order — fundamentals.payload || EXCLUDED.payload keeps
    # EXCLUDED's keys on overlap. Effect: yf is the LAST writer wins
    # if and only if there's no prior key. We mark source='yfinance_history'
    # so audits can tell which rows were yf-derived.
    sql = text("""
        INSERT INTO fundamentals (ticker, period_end, filing_type, payload)
        VALUES (:ticker, :period_end, :filing_type, CAST(:payload AS JSONB))
        ON CONFLICT (ticker, period_end, filing_type)
        DO UPDATE SET
            payload = EXCLUDED.payload || fundamentals.payload,
            fetched_at = NOW()
    """)
    written = 0
    with session_scope() as session:
        for r in rows:
            session.execute(sql, r)
            written += 1
    return written


def ingest(tickers: Iterable[str]) -> IngestResult:
    """Pull historical annual income statements from yfinance.

    Writes one synthetic income row per fiscal year per ticker, tagged
    `period='FY'` so `_annual_income_rows` picks them up. Skips tickers
    where yfinance returns no usable data.
    """
    tickers_list = sorted({t.upper() for t in tickers})
    started = datetime.now()
    log.info("yf_history.start", n_tickers=len(tickers_list))

    rows: list[dict] = []
    no_data: list[str] = []

    for tk in tickers_list:
        time.sleep(THROTTLE_S)
        periods = _fetch_one(tk)
        if not periods:
            no_data.append(tk)
            continue
        for p in periods:
            payload = {
                "source":          "yfinance_history",
                "period":          "FY",
                "fy":              p["fy_end"].year if hasattr(p["fy_end"], "year") else None,
                "epsDiluted":      p["epsDiluted"],
                "revenue":         p["revenue"],
                "grossProfit":     p["grossProfit"],
                "operatingIncome": p["operatingIncome"],
            }
            rows.append({
                "ticker":      tk,
                "period_end":  p["fy_end"],
                "filing_type": "income",
                "payload":     json.dumps(payload),
            })

    written = _upsert(rows)
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="yf_history",
        tickers_processed=len(tickers_list),
        rows_upserted=written,
        tickers_no_data=no_data,
        duration_ms=duration_ms,
    )
    log.info("yf_history.done",
             tickers=len(tickers_list),
             rows=written,
             no_data=len(no_data),
             ms=duration_ms)
    return result

"""FMP fundamentals ingestor.

Pulls income statement, balance sheet, and cash flow statement for the equity
universe. Uses FMP's new `/stable/` endpoints (legacy `/api/v3/*` returns 403).

Free tier limits: ~250 requests/day. With 49 equities × 3 statements = 147
requests for full annual history, well within budget at our daily cadence.

Storage: one row per (ticker, period_end, filing_type) with the raw JSON
payload in `payload` jsonb. Feature builder reads from this to compute
FCF yield, PEG, EPS CAGR, etc. (Phase B, not implemented yet — fundamentals
land in DB now so Phase B has data to play with.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Literal

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from tessera_worker.config import get_settings
from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger
from tessera_worker.universe import by_asset_class

log = get_logger(__name__)

API = "https://financialmodelingprep.com/stable"

FilingType = Literal["income", "balance", "cash_flow"]

_ENDPOINT_BY_TYPE: dict[FilingType, str] = {
    "income":   "income-statement",
    "balance":  "balance-sheet-statement",
    "cash_flow":"cash-flow-statement",
}


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    tickers: list[str]
    rows_upserted: int
    requests_made: int
    duration_ms: int


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch(filing_type: FilingType, ticker: str, period: str, limit: int) -> list[dict]:
    s = get_settings()
    endpoint = _ENDPOINT_BY_TYPE[filing_type]
    r = httpx.get(
        f"{API}/{endpoint}",
        params={
            "symbol": ticker,
            "period": period,        # 'annual' | 'quarter'
            "limit": limit,
            "apikey": s.fmp_api_key,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def _row_for(ticker: str, filing_type: FilingType, payload: dict) -> dict | None:
    # FMP payload always carries `date` (period end). Skip if missing.
    period_end = payload.get("date")
    if not period_end:
        return None
    try:
        period_end_date = date.fromisoformat(period_end[:10])
    except ValueError:
        return None
    return {
        "ticker": ticker,
        "period_end": period_end_date,
        "filing_type": filing_type,
        "payload": payload,
    }


def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO fundamentals (ticker, period_end, filing_type, payload, fetched_at)
        VALUES (:ticker, :period_end, :filing_type, CAST(:payload AS jsonb), NOW())
        ON CONFLICT (ticker, period_end, filing_type) DO UPDATE SET
            payload = EXCLUDED.payload,
            fetched_at = NOW()
    """)
    # psycopg requires dict→jsonb to go through json.dumps
    import json
    chunk = 200
    written = 0
    with session_scope() as session:
        for i in range(0, len(rows), chunk):
            batch = [{**r, "payload": json.dumps(r["payload"])} for r in rows[i : i + chunk]]
            session.execute(sql, batch)
            written += len(batch)
    return written


def ingest(
    tickers: Iterable[str] | None = None,
    period: Literal["annual", "quarter"] = "annual",
    limit: int = 5,
    filing_types: Iterable[FilingType] = ("income", "balance", "cash_flow"),
) -> IngestResult:
    """Pull fundamentals for the given tickers. Default: 5y annual history."""
    if tickers is None:
        tickers = [t.ticker for t in by_asset_class("equity")]
    tickers = sorted(set(tickers))
    filing_types = list(filing_types)
    started = datetime.now()

    log.info("fmp.start", n_tickers=len(tickers), period=period, limit=limit,
             types=filing_types)

    requests_made = 0
    rows: list[dict] = []
    for ticker in tickers:
        for ft in filing_types:
            try:
                payloads = _fetch(ft, ticker, period, limit)
                requests_made += 1
            except httpx.HTTPStatusError as e:
                # Some tickers (e.g., recent IPOs) may 404; that's expected.
                log.warning("fmp.fetch_skip", ticker=ticker, type=ft,
                            status=e.response.status_code)
                continue
            for p in payloads:
                row = _row_for(ticker, ft, p)
                if row:
                    rows.append(row)

    inserted = _upsert(rows)
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="fmp_fundamentals",
        tickers=tickers,
        rows_upserted=inserted,
        requests_made=requests_made,
        duration_ms=duration_ms,
    )
    log.info("fmp.done", rows=inserted, requests=requests_made, ms=duration_ms)
    return result

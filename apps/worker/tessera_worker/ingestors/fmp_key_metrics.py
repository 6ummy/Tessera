"""FMP key-metrics-TTM ingestor — daily marketCap candidate.

FMP's `/stable/key-metrics-ttm?symbol=X` returns trailing-twelve-month
ratios pre-computed from the filings: marketCap, enterpriseValue,
freeCashFlowYieldTTM, peRatioTTM, currentRatioTTM, etc. We pull it
daily and store as a synthetic income row tagged
`source='fmp_key_metrics'`.

Why this exists separately from `fmp_fundamentals.py`:
  - `fmp_fundamentals` pulls annual filings (income/balance/cash_flow)
    with 30-day caching. Those refresh quarterly at best.
  - `key_metrics_ttm` updates whenever FMP recomputes — often daily as
    new closes shift the price-based ratios. It's a *current* mcap
    snapshot, not a quarterly filing snapshot.

Why a separate `period_end` (today - 1 day) instead of the same key as
yf_shares' synthetic row:
  - yf_shares writes `(ticker, today, income)`. Same-key merge would
    collide and create a merge-order dependency (whichever ran later
    would clobber the earlier). Off-by-one date keeps both rows distinct,
    and the loader's per-field newest-non-null walk picks up whichever
    has the field populated.

Storage rationale (using fundamentals table vs new table):
  - `fundamentals` already has the (ticker, period_end, filing_type)
    indexing and JSONB payload pattern. Reusing it means compute.py's
    existing loader picks up the new row with zero changes.

Coverage caveat: FMP key-metrics-ttm requires the ticker to be in their
US-equity master list. ETFs / crypto pairs / a handful of foreign ADRs
return 404 — we treat 404 as "no data, skip" rather than error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable
import json

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from tessera_worker.config import get_settings
from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger
from tessera_worker.universe import by_asset_class

log = get_logger(__name__)

API = "https://financialmodelingprep.com/stable"
ENDPOINT = "key-metrics-ttm"


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    tickers_processed: int
    rows_upserted: int
    tickers_no_data: list[str] = field(default_factory=list)
    duration_ms: int = 0


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=2, max=10),
       reraise=True)
def _fetch_one(ticker: str) -> dict | None:
    """Returns the first (and typically only) TTM-metrics dict for a
    ticker, or None if FMP has no entry. Network errors propagate via
    tenacity's retry."""
    s = get_settings()
    if not s.fmp_api_key:
        return None
    r = httpx.get(
        f"{API}/{ENDPOINT}",
        params={"symbol": ticker, "apikey": s.fmp_api_key},
        timeout=15,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        return None
    return data[0]


def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    # JSONB merge: this ingestor is the authoritative source for the
    # ticker-today-1 row, so EXCLUDED wins on overlap. There's no other
    # writer at that key so this is unambiguous.
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


def ingest(tickers: Iterable[str] | None = None) -> IngestResult:
    """Pull FMP key-metrics-TTM for the equity universe. Synthetic row at
    period_end = yesterday so it doesn't collide with yf_shares' today
    row."""
    if tickers is None:
        tickers = [t.ticker for t in by_asset_class("equity")]
    tickers_list = sorted({t.upper() for t in tickers})
    started = datetime.now()
    log.info("fmp_key_metrics.start", n_tickers=len(tickers_list))

    period_end = date.today() - timedelta(days=1)
    rows: list[dict] = []
    no_data: list[str] = []

    for tk in tickers_list:
        try:
            data = _fetch_one(tk)
        except httpx.HTTPStatusError as e:
            log.warning("fmp_key_metrics.fetch_skip",
                        ticker=tk, status=e.response.status_code)
            no_data.append(tk)
            continue
        if not data:
            no_data.append(tk)
            continue
        # Keep the fields compute.py + the prompt layer actually consult.
        # Full payload is many dozen ratios; we stash the most useful and
        # discard the rest to keep the JSONB row small.
        payload = {
            "source":                   "fmp_key_metrics",
            "marketCap":                _safe_float(data.get("marketCap")),
            "enterpriseValue":          _safe_float(data.get("enterpriseValue")),
            "freeCashFlowYieldTTM":     _safe_float(data.get("freeCashFlowYieldTTM")),
            "peRatioTTM":               _safe_float(data.get("peRatioTTM")),
            "pegRatioTTM":              _safe_float(data.get("pegRatioTTM")),
            "currentRatioTTM":          _safe_float(data.get("currentRatioTTM")),
            "debtToEquityTTM":          _safe_float(data.get("debtToEquityTTM")),
            "returnOnEquityTTM":        _safe_float(data.get("returnOnEquityTTM")),
            "returnOnAssetsTTM":        _safe_float(data.get("returnOnAssetsTTM")),
        }
        if not any(v is not None for k, v in payload.items() if k != "source"):
            no_data.append(tk)
            continue
        rows.append({
            "ticker":      tk,
            "period_end":  period_end,
            "filing_type": "income",
            "payload":     json.dumps(payload),
        })

    written = _upsert(rows)
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="fmp_key_metrics",
        tickers_processed=len(tickers_list),
        rows_upserted=written,
        tickers_no_data=no_data,
        duration_ms=duration_ms,
    )
    log.info("fmp_key_metrics.done",
             tickers=len(tickers_list),
             rows=written,
             no_data=len(no_data),
             ms=duration_ms)
    return result


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f

"""Yahoo (yfinance) EOD bar FALLBACK for `ohlcv_1d`.

Used by `_step_ohlcv_equity` when the primary Alpaca feed is down or stale, so
the price plane (SPY chart, persona books) keeps updating during an Alpaca
outage instead of freezing (which is exactly what happened 2026-06-18, when
Alpaca-sourced bars stopped while every other source kept flowing).

yfinance is an UNOFFICIAL Yahoo scraper — fine as a fallback. Rows are tagged
`source='yahoo'` and only fill calendar days no higher-priority source already
covers: Yahoo stamps 00:00 where Alpaca stamps 04:00Z, so writing both for the
same trading day would create the (ticker, ts) double-row that silently halved
row-window feature horizons (P0-1). Readers dedup by `(ticker, ts::date)` and
prefer alpaca, so these rows only surface where Alpaca is missing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

_UPSERT = text("""
    INSERT INTO ohlcv_1d (ticker, ts, open, high, low, close, volume, vwap, source)
    VALUES (:ticker, :ts, :open, :high, :low, :close, :volume, :vwap, 'yahoo')
    ON CONFLICT (ticker, ts) DO UPDATE SET
        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
        close=EXCLUDED.close, volume=EXCLUDED.volume, vwap=EXCLUDED.vwap,
        source=EXCLUDED.source
""")


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    tickers: list[str]
    rows_upserted: int
    date_range: tuple[date, date] | None
    duration_ms: int


def _to_yahoo_symbol(ticker: str) -> str:
    """Yahoo uses '-' where our universe uses '.' (BRK.B → BRK-B)."""
    return ticker.replace(".", "-")


def _is_nan(x: Any) -> bool:
    return x is None or x != x  # NaN != NaN


def ingest(tickers: Iterable[str], start: date, end: date | None = None) -> IngestResult:
    """Pull daily bars from Yahoo for `tickers`, skipping days another source
    already covers, and upsert as source='yahoo'."""
    import yfinance as yf  # type: ignore[import-untyped]

    ticker_list = sorted(set(tickers))
    end = end or date.today()
    started = datetime.now()
    total = 0
    seen_days: list[date] = []

    log.info("yf_ohlcv.start", tickers=len(ticker_list), start=str(start), end=str(end))
    for ticker in ticker_list:
        try:
            df = yf.Ticker(_to_yahoo_symbol(ticker)).history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
                interval="1d",
                auto_adjust=False,
            )
        except Exception as exc:  # noqa: BLE001 — one ticker must not kill the fallback
            log.warning("yf_ohlcv.ticker_failed", ticker=ticker, err=str(exc))
            continue
        if df is None or df.empty:
            continue

        with session_scope() as session:
            covered = {
                r[0] for r in session.execute(text("""
                    SELECT DISTINCT ts::date FROM ohlcv_1d
                    WHERE ticker = :t AND source <> 'yahoo'
                """), {"t": ticker}).all()
            }

        rows: list[dict[str, Any]] = []
        for idx, row in df.iterrows():
            d = idx.date() if hasattr(idx, "date") else idx
            o, h, low_, c, vol = (row["Open"], row["High"], row["Low"], row["Close"], row["Volume"])
            if any(_is_nan(x) for x in (o, h, low_, c)) or d in covered:
                continue
            rows.append({
                "ticker": ticker, "ts": d,
                "open": float(o), "high": float(h), "low": float(low_), "close": float(c),
                "volume": int(vol) if not _is_nan(vol) and vol else 0, "vwap": None,
            })
            seen_days.append(d)
        if not rows:
            continue
        with session_scope() as session:
            session.execute(_UPSERT, rows)
        total += len(rows)

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    date_range = (min(seen_days), max(seen_days)) if seen_days else None
    log.info("yf_ohlcv.done", rows=total, tickers=len(ticker_list), range=str(date_range))
    return IngestResult("yf_ohlcv", ticker_list, total, date_range, duration_ms)

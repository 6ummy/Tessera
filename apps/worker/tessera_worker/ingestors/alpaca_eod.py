"""Alpaca EOD bar ingestor.

Fetches daily OHLCV bars for a ticker universe via Alpaca Market Data API,
upserts into `ohlcv_1d` (TimescaleDB hypertable). Idempotent.

Free tier note: Alpaca free market data is delayed 15 min and limited to IEX
feed. For EOD bars this is fine — we use the prior-day close.

Usage:
    from datetime import date, timedelta
    from tessera_worker.ingestors.alpaca_eod import ingest

    result = ingest(["SPY", "AAPL"], start=date.today() - timedelta(days=365))
    print(result)  # IngestResult(rows_upserted=502, ...)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from tessera_worker.config import get_settings
from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Per-run audit summary."""

    source: str
    tickers: list[str]
    rows_upserted: int
    date_range: tuple[date, date] | None
    duration_ms: int


def _client() -> StockHistoricalDataClient:
    s = get_settings()
    if not s.alpaca_api_key or not s.alpaca_api_secret:
        raise RuntimeError("ALPACA_API_KEY / ALPACA_API_SECRET not set in env / .env")
    # No `paper=True` here — market data API uses the same credentials regardless
    # of trading mode. The trading mode applies only to the TradingClient.
    return StockHistoricalDataClient(s.alpaca_api_key, s.alpaca_api_secret)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_bars(tickers: list[str], start: date, end: date) -> dict[str, Any]:
    """Fetch daily bars for all tickers in one request. Alpaca returns a
    `BarSet` with `.data` mapping ticker → list[Bar]."""
    client = _client()
    req = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame(amount=1, unit=TimeFrameUnit.Day),
        start=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
        end=datetime.combine(end, datetime.min.time(), tzinfo=UTC),
        feed="iex",  # free tier
        adjustment="all",  # split + dividend adjusted
    )
    bars = client.get_stock_bars(req)
    # alpaca-py returns .data as a dict[str, list[Bar]]
    return bars.data if hasattr(bars, "data") else {}


def _upsert(rows: list[dict[str, Any]]) -> int:
    """Idempotent insert. ON CONFLICT (ticker, ts) DO UPDATE so a re-run
    rewrites the same row with fresh values (handles late corrections)."""
    if not rows:
        return 0
    sql = text("""
        INSERT INTO ohlcv_1d (ticker, ts, open, high, low, close, volume, vwap, source)
        VALUES (:ticker, :ts, :open, :high, :low, :close, :volume, :vwap, :source)
        ON CONFLICT (ticker, ts) DO UPDATE SET
            open   = EXCLUDED.open,
            high   = EXCLUDED.high,
            low    = EXCLUDED.low,
            close  = EXCLUDED.close,
            volume = EXCLUDED.volume,
            vwap   = EXCLUDED.vwap,
            source = EXCLUDED.source
    """)
    with session_scope() as session:
        session.execute(sql, rows)
    return len(rows)


def ingest(
    tickers: Iterable[str],
    start: date,
    end: date | None = None,
) -> IngestResult:
    """Pull EOD bars from Alpaca for the given tickers and date range, upsert."""
    tickers = sorted(set(tickers))
    end = end or date.today()
    started = datetime.now()

    log.info("alpaca_eod.start", tickers=tickers, start=str(start), end=str(end))
    raw = _fetch_bars(tickers, start, end)

    rows: list[dict[str, Any]] = []
    for ticker, bars in raw.items():
        for b in bars:
            # b.timestamp is a timezone-aware datetime at the bar's open time
            rows.append({
                "ticker": ticker,
                "ts": b.timestamp,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": int(b.volume) if b.volume else 0,
                "vwap": float(b.vwap) if b.vwap else None,
                "source": "alpaca",
            })

    inserted = _upsert(rows)

    date_range = None
    if rows:
        date_range = (
            min(r["ts"].date() for r in rows),
            max(r["ts"].date() for r in rows),
        )

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="alpaca_eod",
        tickers=tickers,
        rows_upserted=inserted,
        date_range=date_range,
        duration_ms=duration_ms,
    )
    log.info("alpaca_eod.done", **{
        "rows": inserted,
        "ms": duration_ms,
        "range": str(date_range) if date_range else "none",
    })
    return result

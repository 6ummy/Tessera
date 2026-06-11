"""Coinbase EOD candle ingestor.

Uses Coinbase Exchange public market data API — no auth required for OHLCV.
We pull daily granularity (86400s) for BTC-USD and ETH-USD by default; pass
explicit `pairs=[...]` to override.

Coinbase row shape: [time, low, high, open, close, volume]  (UTC seconds, floats)
Insert into ohlcv_1d with source='coinbase'. Same hypertable as equities so the
feature builder treats them uniformly.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

API = "https://api.exchange.coinbase.com"
GRANULARITY_DAY = 86_400
MAX_CANDLES_PER_REQ = 300  # Coinbase hard cap

# Default crypto universe derives from universe.py's CRYPTO list so the
# canonical source stays one file. Coinbase API uses BTC-USD (dash) while
# we store BTC/USD internally — convert on the fly.
def _default_pairs() -> tuple[str, ...]:
    from tessera_worker.universe import CRYPTO
    return tuple(t.ticker.replace("/", "-") for t in CRYPTO)


DEFAULT_PAIRS = _default_pairs()


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    pairs: list[str]
    rows_upserted: int
    date_range: tuple[date, date] | None
    duration_ms: int


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_window(pair: str, start: datetime, end: datetime) -> list[list[float]]:
    """Fetch ≤300 daily candles between [start, end). Coinbase returns newest first."""
    r = httpx.get(
        f"{API}/products/{pair}/candles",
        params={
            "granularity": GRANULARITY_DAY,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        timeout=15,
        headers={"User-Agent": "tessera-worker/0.1"},
    )
    r.raise_for_status()
    return r.json()


def _fetch_pair(pair: str, start: date, end: date) -> list[list[float]]:
    """Page through windows so we respect the 300-candle limit."""
    all_rows: list[list[float]] = []
    cursor_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(end, datetime.min.time(), tzinfo=UTC)
    while cursor_start < end_dt:
        window_end = min(cursor_start + timedelta(days=MAX_CANDLES_PER_REQ), end_dt)
        chunk = _fetch_window(pair, cursor_start, window_end)
        all_rows.extend(chunk)
        cursor_start = window_end
    return all_rows


def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO ohlcv_1d (ticker, ts, open, high, low, close, volume, vwap, source)
        VALUES (:ticker, :ts, :open, :high, :low, :close, :volume, NULL, :source)
        ON CONFLICT (ticker, ts) DO UPDATE SET
            open   = EXCLUDED.open,
            high   = EXCLUDED.high,
            low    = EXCLUDED.low,
            close  = EXCLUDED.close,
            volume = EXCLUDED.volume,
            source = EXCLUDED.source
    """)
    with session_scope() as session:
        session.execute(sql, rows)
    return len(rows)


def ingest(
    pairs: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> IngestResult:
    """Pull daily candles for the given Coinbase pairs and upsert."""
    pairs = list(pairs) if pairs is not None else list(DEFAULT_PAIRS)
    end = end or date.today()
    start = start or (end - timedelta(days=400))
    started = datetime.now()

    log.info("coinbase_eod.start", pairs=pairs, start=str(start), end=str(end))

    rows: list[dict] = []
    for pair in pairs:
        raw = _fetch_pair(pair, start, end)
        for r in raw:
            # [time, low, high, open, close, volume]
            ts_unix, low, high, op, cl, volume = r
            rows.append({
                "ticker": pair.replace("-", "/"),  # store as 'BTC/USD' for consistency
                "ts": datetime.fromtimestamp(ts_unix, tz=UTC),
                "open": float(op),
                "high": float(high),
                "low": float(low),
                "close": float(cl),
                "volume": int(volume),
                "source": "coinbase",
            })

    inserted = _upsert(rows)
    date_range = (
        (min(r["ts"].date() for r in rows), max(r["ts"].date() for r in rows))
        if rows else None
    )
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="coinbase_eod",
        pairs=pairs,
        rows_upserted=inserted,
        date_range=date_range,
        duration_ms=duration_ms,
    )
    log.info("coinbase_eod.done", rows=inserted, ms=duration_ms,
             range=str(date_range) if date_range else "none")
    return result

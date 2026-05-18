"""FRED macro series ingestor.

Pulls a curated set of ~20 macro series from St Louis Fed FRED API:
yields, inflation, employment, money/credit. Feeds Ray's regime model.

Free, no rate limit issue at our cadence (daily pull, ~20 series).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from tessera_worker.config import get_settings
from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

API = "https://api.stlouisfed.org/fred/series/observations"


# Curated macro universe — meaningful and not over-correlated. Add as needed.
# Each entry: (series_id, human-readable description)
DEFAULT_SERIES: tuple[tuple[str, str], ...] = (
    # ── Yields & curve ──
    ("DGS2",       "2Y Treasury yield"),
    ("DGS10",      "10Y Treasury yield"),
    ("DGS30",      "30Y Treasury yield"),
    ("T10Y2Y",     "10Y - 2Y term spread"),
    ("T10YIE",     "10Y breakeven inflation"),
    ("T5YIFR",     "5Y forward inflation expectation"),
    # ── Inflation & wages ──
    ("CPIAUCSL",   "CPI-U seasonally adjusted (level)"),
    ("CPILFESL",   "Core CPI-U seasonally adjusted (level)"),
    ("PCEPI",      "PCE price index"),
    ("PCEPILFE",   "Core PCE price index"),
    ("CES0500000003", "Avg hourly earnings, private"),
    # ── Labor ──
    ("UNRATE",     "Unemployment rate"),
    ("PAYEMS",     "Nonfarm payrolls"),
    ("ICSA",       "Initial jobless claims"),
    # ── Growth & activity ──
    ("INDPRO",     "Industrial production"),
    ("RSAFS",      "Retail sales"),
    # ── Money / credit / liquidity ──
    ("M2SL",       "M2 money stock"),
    ("WALCL",      "Fed balance sheet"),
    ("DTWEXBGS",   "Trade-weighted USD index (broad goods+services)"),
    # ── Risk ──
    ("VIXCLS",     "CBOE VIX close"),
)


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    series_pulled: int
    rows_upserted: int
    duration_ms: int


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_series(series_id: str, start: date | None = None) -> list[dict]:
    s = get_settings()
    params: dict[str, str | int] = {
        "series_id": series_id,
        "api_key": s.fred_api_key,
        "file_type": "json",
    }
    if start is not None:
        params["observation_start"] = start.isoformat()
    r = httpx.get(API, params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("observations", [])


def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO macro_series (series_id, ts, value)
        VALUES (:series_id, :ts, :value)
        ON CONFLICT (series_id, ts) DO UPDATE SET value = EXCLUDED.value
    """)
    chunk = 1000
    written = 0
    with session_scope() as session:
        for i in range(0, len(rows), chunk):
            session.execute(sql, rows[i : i + chunk])
            written += len(rows[i : i + chunk])
    return written


def ingest(
    series: Iterable[tuple[str, str]] | None = None,
    start: date | None = None,
) -> IngestResult:
    """Pull observations for each series since `start` (default: full history)."""
    series_list = list(series) if series is not None else list(DEFAULT_SERIES)
    started = datetime.now()
    log.info("fred.start", n=len(series_list), start=str(start) if start else "full")

    rows: list[dict] = []
    for series_id, _desc in series_list:
        obs = _fetch_series(series_id, start=start)
        for o in obs:
            # FRED uses "." sentinel for missing observations
            val_raw = o.get("value")
            if val_raw in (".", "", None):
                continue
            try:
                val = float(val_raw)
            except (TypeError, ValueError):
                continue
            rows.append({
                "series_id": series_id,
                "ts": date.fromisoformat(o["date"]),
                "value": val,
            })

    inserted = _upsert(rows)
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="fred_macro",
        series_pulled=len(series_list),
        rows_upserted=inserted,
        duration_ms=duration_ms,
    )
    log.info("fred.done", series=len(series_list), rows=inserted, ms=duration_ms)
    return result

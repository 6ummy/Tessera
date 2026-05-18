"""Deterministic feature builder.

Reads `ohlcv_1d` for a set of tickers, computes price/volume features per
trading day, upserts into `ticker_features`. This is the **only path** by
which numerical features reach the LLM — every number in a Tessera thesis
either flows through here or is rejected by the risk gateway.

Design constraints:
- No I/O beyond DB reads/writes.
- No LLM, no third-party calls.
- Outputs must be reproducible: same OHLCV input → byte-identical features.
- Property-based tests in tests/features/ assert math invariants.

Features computed (price-only for Phase A; valuation + sentiment added later
when fundamentals + news ingestors land):

| Column             | Formula                                                       |
| ------------------ | ------------------------------------------------------------- |
| ret_{1,5,30,90}d, ret_1y | close[t] / close[t-N] - 1                              |
| vol_30d            | std(daily log returns over 30d) * sqrt(252)                  |
| rsi_14             | classic Wilder RSI, 14-period                                 |
| sma_20, sma_50     | simple moving average                                         |
| volume_z           | (volume[t] - mean(volume, 60d)) / std(volume, 60d)            |
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

# Lookback windows
RET_HORIZONS = {"ret_1d": 1, "ret_5d": 5, "ret_30d": 30, "ret_90d": 90, "ret_1y": 252}
VOL_WINDOW = 30
RSI_WINDOW = 14
SMA_WINDOWS = (20, 50)
VOLUME_Z_WINDOW = 60
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class FeatureResult:
    tickers: list[str]
    rows_written: int
    date_range: tuple[date, date] | None
    duration_ms: int


# ─────────────────────────────────────────────────────────────────────────
# Pure-function feature math. Inputs are pandas Series; no I/O.
# These are the functions the property-based tests target.
# ─────────────────────────────────────────────────────────────────────────

def pct_change(close: pd.Series, n: int) -> pd.Series:
    """Total return over N trading days, using close-to-close."""
    return close / close.shift(n) - 1.0


def realized_vol(close: pd.Series, window: int = VOL_WINDOW) -> pd.Series:
    """Annualized realized vol from log returns over `window` days."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)


def rsi(close: pd.Series, window: int = RSI_WINDOW) -> pd.Series:
    """Classic Wilder RSI. Returns 0..100. The first `window` rows are NaN."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # Wilder smoothing == EMA with alpha = 1/window
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    # If all losses are zero (pure uptrend), RSI saturates at 100
    out = out.where(~((avg_loss == 0.0) & (avg_gain > 0.0)), 100.0)
    return out


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window).mean()


def volume_zscore(volume: pd.Series, window: int = VOLUME_Z_WINDOW) -> pd.Series:
    """Z-score of volume vs trailing window. NaN when std == 0 (always-flat)."""
    mu = volume.rolling(window).mean()
    sd = volume.rolling(window).std(ddof=1)
    return (volume - mu) / sd.replace(0.0, np.nan)


# ─────────────────────────────────────────────────────────────────────────
# Pipeline: load → compute → write
# ─────────────────────────────────────────────────────────────────────────

def _load_ohlcv(tickers: list[str]) -> pd.DataFrame:
    """Return tidy DataFrame: index=(ticker, ts), columns=open/high/low/close/volume."""
    sql = text("""
        SELECT ticker, ts, open, high, low, close, volume
        FROM ohlcv_1d
        WHERE ticker = ANY(:tickers)
        ORDER BY ticker, ts
    """)
    with session_scope() as session:
        rows = session.execute(sql, {"tickers": tickers}).all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ticker", "ts", "open", "high", "low", "close", "volume"])
    # Decimal → float for math
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype("Int64").astype(float)
    return df.set_index(["ticker", "ts"])


def _compute_for_ticker(df_t: pd.DataFrame) -> pd.DataFrame:
    """All features for one ticker. Returns DataFrame indexed by ts."""
    close = df_t["close"]
    vol = df_t["volume"]

    out = pd.DataFrame(index=df_t.index)
    for col, n in RET_HORIZONS.items():
        out[col] = pct_change(close, n)
    out["vol_30d"] = realized_vol(close, VOL_WINDOW)
    out["rsi_14"] = rsi(close, RSI_WINDOW)
    for n in SMA_WINDOWS:
        out[f"sma_{n}"] = sma(close, n)
    out["volume_z"] = volume_zscore(vol, VOLUME_Z_WINDOW)
    return out


def _upsert_features(frames: dict[str, pd.DataFrame]) -> int:
    """Upsert one row per (ticker, ts). Idempotent via ON CONFLICT."""
    rows: list[dict] = []
    for ticker, df in frames.items():
        # Drop rows where every feature is NaN (early-history padding)
        df = df.dropna(how="all")
        for ts, r in df.iterrows():
            rows.append({
                "ticker": ticker,
                "ts": ts,
                "ret_1d":   _f(r.get("ret_1d")),
                "ret_5d":   _f(r.get("ret_5d")),
                "ret_30d":  _f(r.get("ret_30d")),
                "ret_90d":  _f(r.get("ret_90d")),
                "ret_1y":   _f(r.get("ret_1y")),
                "vol_30d":  _f(r.get("vol_30d")),
                "rsi_14":   _f(r.get("rsi_14")),
                "sma_20":   _f(r.get("sma_20")),
                "sma_50":   _f(r.get("sma_50")),
                "volume_z": _f(r.get("volume_z")),
            })
    if not rows:
        return 0
    sql = text("""
        INSERT INTO ticker_features (
            ticker, ts,
            ret_1d, ret_5d, ret_30d, ret_90d, ret_1y,
            vol_30d, rsi_14, sma_20, sma_50, volume_z
        ) VALUES (
            :ticker, :ts,
            :ret_1d, :ret_5d, :ret_30d, :ret_90d, :ret_1y,
            :vol_30d, :rsi_14, :sma_20, :sma_50, :volume_z
        )
        ON CONFLICT (ticker, ts) DO UPDATE SET
            ret_1d   = EXCLUDED.ret_1d,
            ret_5d   = EXCLUDED.ret_5d,
            ret_30d  = EXCLUDED.ret_30d,
            ret_90d  = EXCLUDED.ret_90d,
            ret_1y   = EXCLUDED.ret_1y,
            vol_30d  = EXCLUDED.vol_30d,
            rsi_14   = EXCLUDED.rsi_14,
            sma_20   = EXCLUDED.sma_20,
            sma_50   = EXCLUDED.sma_50,
            volume_z = EXCLUDED.volume_z
    """)
    # Chunk to keep prepared statement size reasonable
    chunk = 500
    written = 0
    with session_scope() as session:
        for i in range(0, len(rows), chunk):
            session.execute(sql, rows[i : i + chunk])
            written += len(rows[i : i + chunk])
    return written


def _f(v) -> float | None:
    """NaN-aware Decimal-friendly coerce to plain float for psycopg binding."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float) and (v != v):  # NaN
        return None
    if pd.isna(v):
        return None
    return float(v)


def build(tickers: list[str]) -> FeatureResult:
    """Recompute features for the given tickers from current ohlcv_1d state."""
    started = datetime.now()
    log.info("features.build.start", n_tickers=len(tickers))

    df = _load_ohlcv(tickers)
    if df.empty:
        log.warning("features.build.no_data", tickers=tickers)
        return FeatureResult(tickers=tickers, rows_written=0, date_range=None,
                             duration_ms=int((datetime.now() - started).total_seconds() * 1000))

    frames: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        if ticker not in df.index.get_level_values(0):
            continue
        df_t = df.loc[ticker].sort_index()
        frames[ticker] = _compute_for_ticker(df_t)

    written = _upsert_features(frames)

    all_ts = []
    for df_t in frames.values():
        all_ts.extend(df_t.index.tolist())
    date_range = (
        (min(all_ts).date(), max(all_ts).date()) if all_ts else None
    )

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = FeatureResult(
        tickers=sorted(frames.keys()),
        rows_written=written,
        date_range=date_range,
        duration_ms=duration_ms,
    )
    log.info("features.build.done", rows=written, ms=duration_ms, n_tickers=len(frames))
    return result

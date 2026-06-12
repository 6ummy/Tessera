"""Parametric VaR + drawdown inputs for the risk gateway.

Pure math on aligned daily log-returns, plus thin DB loaders that build a
`MarketContext` for the gateway. Kept separate from gateway.py so the
math is unit-testable with synthetic series and the gateway stays a pure
rule-checker over inputs it's handed.

Method (Plan §5 Week 4): one-day parametric VaR at 99% —
    VaR99 = z99 × sqrt(wᵀ Σ w)
where Σ is the sample covariance of daily log returns over the trailing
window (≤252 obs, ≥60 required) and w are the book's NAV weights. Cash
contributes zero variance, so only risky positions enter w. This is the
classic delta-normal estimate: cheap, deterministic, and good enough to
catch a book whose gross risk drifted far past the persona's mandate —
NOT a tail model (normality understates fat tails; crypto especially).
Thresholds in persona_constraints carry headroom for that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.logging import get_logger

log = get_logger(__name__)

Z_99 = 2.326  # one-sided 99% normal quantile
RETURN_WINDOW_OBS = 252
MIN_OBS = 60


@dataclass(frozen=True, slots=True)
class MarketContext:
    """Everything the gateway's market-dependent checks need.

    returns: ticker → daily log returns, date-ALIGNED across tickers
             (same length, same calendar) — required for the covariance.
    current_drawdown: the persona's live-track drawdown from peak
             (positive fraction), None when the track is too young.
    """

    returns: dict[str, list[float]]
    current_drawdown: float | None


# ─────────────────────────────────────────────────────────────────────────
# Pure math
# ─────────────────────────────────────────────────────────────────────────

def align_log_returns(
    closes: dict[str, dict[date, float]],
) -> dict[str, list[float]]:
    """Daily log returns over the INTERSECTION of all tickers' dates.

    Mixed calendars (crypto trades weekends, equities don't) make naive
    per-ticker returns non-comparable for covariance; intersecting dates
    keeps every return vector on the same clock. Tickers with no data
    drop out (caller decides how to treat them)."""
    usable = {t: d for t, d in closes.items() if len(d) >= 2}
    if not usable:
        return {}
    common = set.intersection(*(set(d.keys()) for d in usable.values()))
    days = sorted(common)
    if len(days) < 2:
        return {}
    out: dict[str, list[float]] = {}
    for ticker, by_date in usable.items():
        series = [by_date[d] for d in days]
        out[ticker] = [
            math.log(series[i] / series[i - 1])
            for i in range(1, len(series))
            if series[i - 1] > 0 and series[i] > 0
        ]
    # Guard: positive-price filter above could desync lengths in corrupt
    # data; covariance needs equal lengths. Trim to the shortest.
    n = min(len(v) for v in out.values())
    return {t: v[-n:] for t, v in out.items()}


def parametric_var99(
    weights: dict[str, float],
    returns: dict[str, list[float]],
    *,
    min_obs: int = MIN_OBS,
) -> float | None:
    """One-day 99% parametric VaR of the book as a positive fraction of
    NAV. None when fewer than `min_obs` aligned observations exist for
    the weighted tickers (young listings) — the caller treats that as
    "can't assess", not "safe"."""
    tickers = [t for t, w in weights.items() if w > 0 and t in returns]
    if not tickers:
        return None
    n = min(len(returns[t]) for t in tickers)
    if n < min_obs:
        return None
    n = min(n, RETURN_WINDOW_OBS)
    matrix = np.array([returns[t][-n:] for t in tickers])
    w = np.array([weights[t] for t in tickers])
    if len(tickers) == 1:
        variance = float(np.var(matrix[0], ddof=1)) * float(w[0]) ** 2
    else:
        cov = np.cov(matrix)
        variance = float(w @ cov @ w)
    if variance <= 0:
        return 0.0
    return Z_99 * math.sqrt(variance)


def current_drawdown(values: list[float]) -> float | None:
    """Drawdown of the LAST value from the running peak (positive
    fraction). None with fewer than 2 points."""
    if len(values) < 2:
        return None
    peak = max(values)
    last = values[-1]
    if peak <= 0:
        return None
    return max(0.0, (peak - last) / peak)


# ─────────────────────────────────────────────────────────────────────────
# DB loaders
# ─────────────────────────────────────────────────────────────────────────

def load_market_context(
    session: Session,
    tickers: list[str],
    persona: str,
    *,
    window_days: int = 400,
) -> MarketContext:
    """Build the gateway's market inputs: aligned returns for the book's
    tickers (post-006 canonical rows, so no source dedup needed) + the
    persona's live-track drawdown (hypothetical rows excluded — the
    backfill is a chart artifact, not risk history)."""
    closes: dict[str, dict[date, float]] = {}
    if tickers:
        rows = session.execute(text("""
            SELECT ticker, ts::date AS d, close
            FROM ohlcv_1d
            WHERE ticker = ANY(:t)
              AND ts >= NOW() - make_interval(days => :w)
              AND close IS NOT NULL
            ORDER BY ticker, d
        """), {"t": sorted(set(tickers)), "w": window_days}).all()
        for r in rows:
            closes.setdefault(r.ticker, {})[r.d] = float(r.close)

    dd_rows = session.execute(text("""
        SELECT total_value FROM persona_portfolios
        WHERE persona_id = :p AND NOT hypothetical
        ORDER BY ts ASC
    """), {"p": persona}).all()
    dd = current_drawdown([float(r.total_value) for r in dd_rows])

    return MarketContext(
        returns=align_log_returns(closes),
        current_drawdown=dd,
    )

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
| fcf_yield          | trailing FCF / market cap (point-in-time, ADR-adjusted)       |
| eps_cagr_3y        | diluted EPS CAGR over roughly 3 fiscal years                  |
| peg                | trailing P/E divided by EPS CAGR percentage                   |
| debt_to_equity     | total debt / stockholders' equity                             |
| gross_margin       | gross profit / revenue                                        |
| gross_margin_trend | latest gross margin minus roughly-3y-ago gross margin         |
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

# ─────────────────────────────────────────────────────────────────────────
# ADR share ratios: 1 ADR = N common shares.
#
# Why this exists: fundamentals providers (FMP and similar) report
# `weightedAverageShsOut` as TOTAL COMMON SHARES of the foreign issuer,
# while `close` is quoted PER ADR. Naïvely computing `mcap = close * shares`
# inflates market cap by the ratio and crushes fcf_yield (or, depending on
# which side is mis-counted, blows it up — TSM showed 48% in the Phase A
# demo for exactly this reason).
#
# Fix: divide common-share count by the ADR ratio so the unit matches close.
# Ratios are official sponsor-bank disclosures; if a name is added to the
# universe and its ratio isn't listed here, we fall back to 1 with a warning.
# ─────────────────────────────────────────────────────────────────────────
ADR_SHARE_RATIOS: dict[str, int] = {
    # Empty by default. Populate only when you confirm a data provider
    # returns COMMON (foreign-issuer total) share counts for a given
    # ticker — in which case dividing by the ratio yields the ADR
    # equivalent that matches per-ADR close.
    #
    # FMP, the provider we use for fundamentals, returns ADR-equivalent
    # share counts for the ADRs in our pilot universe (verified for TSM,
    # ASML). Dividing again here would double-divide and 5× undercount
    # market cap. Leaving entries empty means `_market_cap_from_shares`
    # treats `shares_common` as already ADR-equivalent — correct for FMP.
}

# Above this absolute value, fcf_yield is almost certainly a data bug
# (units mismatch, stale denominator, currency). We log + drop rather
# than feed garbage into the LLM prompt.
FCF_YIELD_SANITY_BOUND = 1.0   # ±100%
EPS_CAGR_SANITY_BOUND = 2.0    # ±200%
PEG_SANITY_BOUND = 100.0
DEBT_TO_EQUITY_SANITY_BOUND = 50.0
MARGIN_SANITY_LOW = -1.0
MARGIN_SANITY_HIGH = 1.0

# ─────────────────────────────────────────────────────────────────────────
# FX conversion: financial data providers report `freeCashFlow` in the
# issuer's local currency (TSM in TWD, ASML's parent entity in EUR, …),
# while `close` is quoted on the US ADR in USD. We compute fcf_yield as
# USD/USD, so FCF must be converted to USD before dividing.
#
# Hardcoded rates: pragmatic for the ~50-name pilot universe. A proper
# daily FX feed (FRED DEXTWUS, DEXUSEU) is a Phase C task. Rates here
# are mid-2026 spot averages — accurate enough for relative comparison
# across personas, not for trading.
#
# How it's used: if `reportedCurrency` in the payload != "USD", we
# multiply the local-currency FCF by FX_TO_USD[ccy] before dividing.
# Unknown currency → log + drop (don't guess).
# ─────────────────────────────────────────────────────────────────────────
FX_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "TWD": 1.0 / 32.0,   # ~32 TWD per USD
    "EUR": 1.08,         # ~1.08 USD per EUR
    "GBP": 1.27,
    "JPY": 1.0 / 155.0,
    "KRW": 1.0 / 1370.0,
    "HKD": 1.0 / 7.8,
    "CNY": 1.0 / 7.2,
    "CAD": 1.0 / 1.36,
}


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
# Fundamentals features — pure functions
# ─────────────────────────────────────────────────────────────────────────

def _market_cap_from_shares(
    close: float | None,
    shares_common: float | None,
    ticker: str | None = None,
) -> float | None:
    """Market cap from price × ADR-adjusted shares.

    `shares_common` is the foreign issuer's total common-share count as
    reported in the income filing. For ADRs, we divide by the sponsor-bank
    ratio so the unit matches the per-ADR `close`. For US-domiciled names
    (default ratio 1) this is a no-op.

    Note: this is ONE candidate the cross-validator considers; data
    providers are inconsistent about whether they report common or
    ADR-equivalent share counts. `estimate_market_cap` runs this against
    other sources and picks the consensus value.
    """
    if close is None or shares_common is None:
        return None
    if close <= 0 or shares_common <= 0:
        return None
    ratio = ADR_SHARE_RATIOS.get(ticker, 1) if ticker else 1
    shares_adr_equivalent = shares_common / ratio
    return close * shares_adr_equivalent


# ─────────────────────────────────────────────────────────────────────────
# Cross-validation: market cap from multiple candidates.
#
# Why we need this: real-world fundamentals data is messy.
# - FMP returns `weightedAverageShsOut` and `weightedAverageShsOutDil`
#   for EPS computation — often slightly off from "true" shares outstanding.
# - For ADRs, providers inconsistently report common-share count vs
#   ADR-equivalent count. (TSM shows 5.19B in FMP, which already looks
#   ADR-equivalent — but we can't tell without ground truth.)
# - `payload.marketCap` is sometimes populated, sometimes null, and when
#   present is from the filing date (frozen between quarters).
# - Multiple share classes (GOOGL Class A/C, BRK Class A/B) split totals
#   across rows.
#
# Single-source picks fail unpredictably across the universe. Cross-
# validation makes failure visible AND systematic:
#   1. Collect all candidates from all sources.
#   2. If they agree (within `max_spread`), trust the freshest (close × shares).
#   3. If they disagree, pick the LARGEST. Rationale:
#      - Undercount errors (missing share class, wrong-unit shares) are
#        more common than overcount.
#      - Larger mcap → lower fcf_yield → more conservative for the LLM
#        prompt. We'd rather understate a value name than overstate one.
#   4. Log every disagreement so we can audit which tickers are systemic
#      problems.
# ─────────────────────────────────────────────────────────────────────────

McapCandidate = tuple[str, float]  # (label, value)


def cross_validated(
    candidates: list[McapCandidate],
    *,
    max_spread: float = 2.0,
    pick_on_disagreement: str = "max",
    log_label: str = "cross_validated",
    ticker: str | None = None,
) -> float | None:
    """Reusable cross-validation. Used here for mcap; applies cleanly to
    any quant ratio where multiple data sources should agree."""
    valid = [(lbl, v) for lbl, v in candidates if v is not None and v > 0]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0][1]
    vals = [v for _, v in valid]
    spread = max(vals) / min(vals)
    if spread > max_spread:
        log.warning(
            f"features.{log_label}.disagreement",
            ticker=ticker, candidates=valid, spread=round(spread, 2),
            decision=pick_on_disagreement,
        )
        return max(vals) if pick_on_disagreement == "max" else min(vals)
    # In agreement — return the first (caller orders by trust)
    return valid[0][1]


def estimate_market_cap(
    *,
    close: float | None,
    shares_basic: float | None,
    shares_diluted: float | None,
    payload_mcap_cash: float | None = None,
    payload_mcap_income: float | None = None,
    ticker: str | None = None,
) -> float | None:
    """Best-effort USD market cap from 4 candidates with cross-validation.

    Ordering reflects trust priority (used when candidates agree):
      1. close × shares_diluted (most-current price × inclusive share count)
      2. close × shares_basic
      3. payload_mcap_cash    (stale-by-a-quarter but a real reported number)
      4. payload_mcap_income
    """
    candidates: list[McapCandidate] = []
    mc_d = _market_cap_from_shares(close, shares_diluted, ticker=ticker)
    if mc_d is not None:
        candidates.append(("close×diluted", mc_d))
    mc_b = _market_cap_from_shares(close, shares_basic, ticker=ticker)
    if mc_b is not None:
        candidates.append(("close×basic", mc_b))
    if payload_mcap_cash is not None and payload_mcap_cash > 0:
        candidates.append(("payload_cash", float(payload_mcap_cash)))
    if payload_mcap_income is not None and payload_mcap_income > 0:
        candidates.append(("payload_income", float(payload_mcap_income)))

    return cross_validated(
        candidates, max_spread=2.0, pick_on_disagreement="max",
        log_label="market_cap", ticker=ticker,
    )


def compute_fcf_yield(
    close: float | None,
    fcf_local: float | None,
    *,
    shares_basic: float | None = None,
    shares_diluted: float | None = None,
    reported_currency: str | None = "USD",
    payload_mcap_cash: float | None = None,
    payload_mcap_income: float | None = None,
    ticker: str | None = None,
    # Legacy positional kwarg, accepted for back-compat with v1 callers
    shares_common: float | None = None,
    payload_market_cap: float | None = None,
) -> float | None:
    """Trailing-twelve-month FCF / today's market cap. USD/USD.

    Market cap is estimated via `estimate_market_cap()` — cross-validation
    over 4 candidates (close × diluted, close × basic, payload mcap from
    cash and income filings) with disagreement-detection and conservative
    (max) fallback. See that function's docstring for rationale.

    Currency: `fcf_local` is in `reported_currency`. We convert to USD via
    FX_TO_USD before dividing. Unknown currency → drop.

    Returns None when fcf is missing, currency is unknown, no mcap
    candidate can be built, or the result exceeds ±FCF_YIELD_SANITY_BOUND.

    Back-compat: `shares_common` and `payload_market_cap` are accepted
    as aliases for the basic-share / cash-payload candidates so legacy
    tests + call sites keep working.
    """
    if fcf_local is None:
        return None

    # FX → USD
    ccy = (reported_currency or "USD").upper()
    fx = FX_TO_USD.get(ccy)
    if fx is None:
        log.warning("features.fcf_yield.unknown_currency",
                    ticker=ticker, reported_currency=ccy)
        return None
    fcf_usd = float(fcf_local) * fx

    # Cross-validated market cap. Back-compat aliases fold in.
    eff_basic = shares_basic if shares_basic is not None else shares_common
    eff_mcap_cash = payload_mcap_cash if payload_mcap_cash is not None else payload_market_cap

    mcap = estimate_market_cap(
        close=close,
        shares_basic=eff_basic,
        shares_diluted=shares_diluted,
        payload_mcap_cash=eff_mcap_cash,
        payload_mcap_income=payload_mcap_income,
        ticker=ticker,
    )
    if mcap is None or mcap <= 0:
        return None

    yld = fcf_usd / mcap
    if abs(yld) > FCF_YIELD_SANITY_BOUND:
        log.warning(
            "features.fcf_yield.sanity_drop",
            ticker=ticker, fcf_usd=fcf_usd, market_cap=mcap, computed=yld,
            reported_currency=ccy,
            note="exceeds ±100%; likely units mismatch — dropping",
        )
        return None
    return yld


def compute_eps_cagr_3y(rows: list[dict]) -> float | None:
    """3-year diluted EPS CAGR from annual income rows.

    `rows` should be newest first and carry `period_end` plus `epsDiluted`
    or `epsBasic`. We prefer a row roughly three fiscal years before the
    latest observation; if dates are sparse but at least four annual rows
    exist, the fourth row is used as the fallback anchor.
    """
    annual = _annual_income_rows(rows)
    if len(annual) < 4:
        return None

    latest = annual[0]
    latest_eps = _eps_value(latest)
    latest_pe = latest.get("period_end")
    if latest_eps is None or latest_eps <= 0 or latest_pe is None:
        return None

    anchor = None
    for row in annual[1:]:
        pe = row.get("period_end")
        if pe is None:
            continue
        delta_days = (latest_pe - pe).days
        if 900 <= delta_days <= 1280:
            anchor = row
            break
    if anchor is None and len(annual) >= 4:
        anchor = annual[3]

    if anchor is None:
        return None
    anchor_eps = _eps_value(anchor)
    anchor_pe = anchor.get("period_end")
    if anchor_eps is None or anchor_eps <= 0 or anchor_pe is None:
        return None

    years = (latest_pe - anchor_pe).days / 365.25
    if years < 2.5:
        return None

    cagr = (latest_eps / anchor_eps) ** (1.0 / years) - 1.0
    if abs(cagr) > EPS_CAGR_SANITY_BOUND:
        return None
    return cagr


def compute_peg(
    close: float | None,
    latest_eps: float | None,
    eps_cagr_3y: float | None,
) -> float | None:
    """Trailing PEG proxy: P/E divided by EPS growth as a percent.

    The backlog called this `peg_ratio` and noted that true forward PEG
    needs analyst estimates. We use trailing P/E until an estimates feed
    lands, while keeping the DB column name `peg`.
    """
    if close is None or latest_eps is None or eps_cagr_3y is None:
        return None
    if close <= 0 or latest_eps <= 0 or eps_cagr_3y <= 0:
        return None
    trailing_pe = close / latest_eps
    peg = trailing_pe / (eps_cagr_3y * 100.0)
    if peg <= 0 or peg > PEG_SANITY_BOUND:
        return None
    return peg


def compute_debt_to_equity(
    *,
    total_debt: float | None = None,
    long_term_debt: float | None = None,
    short_term_debt: float | None = None,
    equity: float | None = None,
) -> float | None:
    """Total debt / stockholders' equity."""
    if equity is None or equity <= 0:
        return None
    debt = total_debt
    if debt is None:
        parts = [v for v in (long_term_debt, short_term_debt) if v is not None and v > 0]
        if not parts:
            return None
        debt = sum(parts)
    if debt < 0:
        return None
    ratio = debt / equity
    if ratio > DEBT_TO_EQUITY_SANITY_BOUND:
        return None
    return ratio


def compute_gross_margin(revenue: float | None, gross_profit: float | None) -> float | None:
    """Gross profit / revenue, with conservative sanity bounds."""
    if revenue is None or gross_profit is None or revenue <= 0:
        return None
    margin = gross_profit / revenue
    if margin < MARGIN_SANITY_LOW or margin > MARGIN_SANITY_HIGH:
        return None
    return margin


def compute_gross_margin_trend(rows: list[dict]) -> float | None:
    """Latest gross margin minus gross margin roughly three years prior."""
    annual = _annual_income_rows(rows)
    if len(annual) < 4:
        return None

    latest = annual[0]
    latest_margin = compute_gross_margin(
        _to_float(latest.get("revenue")),
        _to_float(latest.get("grossProfit")),
    )
    latest_pe = latest.get("period_end")
    if latest_margin is None or latest_pe is None:
        return None

    anchor = None
    for row in annual[1:]:
        pe = row.get("period_end")
        if pe is None:
            continue
        delta_days = (latest_pe - pe).days
        if 900 <= delta_days <= 1280:
            anchor = row
            break
    if anchor is None:
        anchor = annual[3]

    anchor_margin = compute_gross_margin(
        _to_float(anchor.get("revenue")),
        _to_float(anchor.get("grossProfit")),
    )
    if anchor_margin is None:
        return None
    return latest_margin - anchor_margin


def sum_ttm_fcf(rows: list[dict]) -> float | None:
    """Trailing-twelve-month FCF — robust to three data shapes.

    `rows` are most-recent first, each with `freeCashFlow`, optional
    `period` ("Q1"/"Q2"/"Q3"/"Q4"/"FY" or None), and optional
    `period_end` (`date`).

    The three shapes we've seen in real data:

      (A) Annual-only filings (e.g. TSM): each row is one full fiscal
          year. `period` = "FY". Latest row is already TTM-equivalent.

      (B) Per-quarter standalone (theoretical / some providers):
          each row is one quarter's FCF. Sum the latest 4.

      (C) Cumulative-YTD-per-fiscal-year (FMP, the provider we use):
          row.freeCashFlow = "FCF since start of this fiscal year, as
          of period_end". Q1 = 3 months YTD, Q2 = 6 months, Q4 = full
          annual. Two paths:

            (C-precise)  when period_end is present on rows, decompose
                         into true TTM via:
                           TTM = last_full_FY
                                 + current_YTD
                                 − prior_FY_YTD_at_same_period
                         See `_decompose_cumulative_ytd_to_ttm`.

            (C-fallback) when period_end is missing, approximate as
                         max(window) = the last fiscal-year annual.
                         Up to ~12 months stale for fast growers.

    Returns None when fewer than 4 non-FY rows are present and detection
    doesn't fire (partial-year FCF is misleading — drop rather than
    ship a low-balled yield).
    """
    if not rows:
        return None

    # Shape (A): latest is annual FY → already TTM.
    first_period = (rows[0].get("period") or "").upper()
    if first_period in ("FY", "Q4"):
        return _fcf_value(rows[0])

    # Shape (C): cumulative-YTD detection via 6-row max/min ratio.
    # FMP's pattern: Q1≈X, Q2≈2X, Q3≈3X, Q4≈4X, then resets to ≈X again.
    # Heuristic only fires when periods are ALL None — when the provider
    # gives us explicit Q1/Q2/Q3/Q4/FY labels, we trust them (Shape A/B).
    all_periods_unlabelled = all(
        not (r.get("period") or "").strip() for r in rows
    )
    if all_periods_unlabelled:
        window = [r for r in rows if _fcf_value(r) is not None][:8]
        vals = [_fcf_value(r) for r in window]
        if len(window) >= 4:
            pos = [v for v in vals if v > 0]
            # Threshold 2.0: cumulative shape has max ≈ 4×Q1 ≈ 4×min;
            # genuinely quarterly stays within ~1.5×.
            if len(pos) >= 4 and (max(pos) / min(pos)) > 2.0:
                # (C-precise) Try period_end-aware decomposition.
                ttm = _decompose_cumulative_ytd_to_ttm(window)
                if ttm is not None:
                    return ttm
                # (C-fallback) Last fiscal-year annual ≈ TTM.
                return max(vals)

    # Shape (B): treat as quarterly, sum 4 non-FY rows.
    qs: list[float] = []
    for r in rows:
        period = (r.get("period") or "").upper()
        if period == "FY":
            continue
        v = _fcf_value(r)
        if v is None:
            continue
        qs.append(v)
        if len(qs) == 4:
            break
    if len(qs) < 4:
        return None
    return sum(qs)


def _fcf_value(r: dict) -> float | None:
    v = r.get("freeCashFlow")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _eps_value(r: dict) -> float | None:
    diluted = _to_float(r.get("epsDiluted"))
    if diluted is not None:
        return diluted
    return _to_float(r.get("epsBasic"))


def _annual_income_rows(rows: list[dict]) -> list[dict]:
    """Return newest-first income rows that look annual/FY.

    FMP annual rows carry `period=FY`; SEC companyfacts rows carry
    `form=10-K` and/or `fp=FY`. If a provider omitted those markers, do
    not guess here — annual math is safer as None than as quarterly data
    accidentally annualized.
    """
    out = []
    for row in rows:
        period = (row.get("period") or "").upper()
        form = (row.get("form") or "").upper()
        fp = (row.get("fp") or "").upper()
        if period in ("FY", "Q4") or form == "10-K" or fp == "FY":
            out.append(row)
    out.sort(key=lambda r: r.get("period_end") or date.min, reverse=True)
    return out


def _decompose_cumulative_ytd_to_ttm(rows: list[dict]) -> float | None:
    """Precise TTM from cumulative-YTD rows when period_end is present.

    The math:
        TTM_as_of_current_YTD
          = (last full fiscal year's annual FCF)
            + (current YTD FCF)
            − (prior fiscal year's YTD at the same calendar offset)

    Why this works: the prior-FY-same-YTD term removes the months
    already counted in the last-full-FY annual, and the current-YTD
    adds the same number of months from the new fiscal year — netting
    out to exactly 12 months ending at the current YTD's period_end.

    Worked example for AAPL Q2 FY26 (2026-03-28):
        last_FY        = FY25 annual (period_end 2025-09-27) = $98.77B
        current_YTD    = Q2 FY26 (period_end 2026-03-28)     = $78.28B
        prior_FY_YTD   = Q2 FY25 (period_end 2025-03-29)     = $47.88B
        TTM            = 98.77 + 78.28 − 47.88               = $129.17B
                         (matches independently-computed Apple TTM
                         for the trailing 12 months ending Mar 28 2026.)

    Returns None when any of:
      - period_end missing on any candidate row,
      - no row found ~365 days before the latest (±45-day tolerance),
      - no FY annual candidate found between prior YTD and current YTD,
      - latest row's period_end is younger than ~12 months from any prior
        (universe too sparse to do TTM decomposition).
    """
    dated = []
    for r in rows:
        pe = r.get("period_end")
        if pe is None:
            continue
        dated.append((pe, r))
    if len(dated) < 3:
        return None

    # Sort by period_end DESC — latest first.
    dated.sort(key=lambda x: x[0], reverse=True)
    latest_pe, latest_row = dated[0]
    current_ytd = _fcf_value(latest_row)
    if current_ytd is None:
        return None

    # Find row ~365 days before the latest (320–410 day tolerance: handles
    # 5-week month variance + occasional 53-week fiscal years).
    prior_ytd_row = None
    prior_pe = None
    for pe, r in dated[1:]:
        delta_days = (latest_pe - pe).days
        if 320 <= delta_days <= 410:
            prior_ytd_row = r
            prior_pe = pe
            break
    if prior_ytd_row is None:
        return None
    prior_ytd = _fcf_value(prior_ytd_row)
    if prior_ytd is None:
        return None

    # The "last full FY" is the row strictly between prior_pe and latest_pe
    # with the LARGEST freeCashFlow value (= the fiscal year end inside
    # the window, the only row that's a full-12-month cumulative).
    fy_candidates: list[float] = []
    for pe, r in dated:
        if pe <= prior_pe or pe >= latest_pe:
            continue
        v = _fcf_value(r)
        if v is not None:
            fy_candidates.append(v)
    if not fy_candidates:
        return None
    last_fy_annual = max(fy_candidates)

    return last_fy_annual + current_ytd - prior_ytd


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


def _int_or_none(v) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


# ─────────────────────────────────────────────────────────────────────────
# Fundamentals loader + latest-row upsert
# ─────────────────────────────────────────────────────────────────────────

def _load_fundamentals_latest(tickers: list[str]) -> dict[str, dict]:
    """Recent cash-flow/income rows + latest balance row per ticker.

    Cash flow: pulls up to 4 most-recent rows so the caller can compute
    TTM FCF via `sum_ttm_fcf`. Returns each row's freeCashFlow + period
    + reportedCurrency so currency conversion can happen downstream.

    Income: pulls recent rows for shares outstanding, EPS CAGR, PEG, and
    gross-margin/trend. The latest row with share data supplies the mcap
    denominator candidates.

    Balance: pulls one latest row for debt/equity.
    """
    cash_sql = text("""
        SELECT ticker, period_end,
               payload ->> 'freeCashFlow'     AS fcf,
               payload ->> 'period'           AS period,
               payload ->> 'reportedCurrency' AS ccy,
               payload ->> 'marketCap'        AS market_cap
        FROM fundamentals
        WHERE ticker = ANY(:t) AND filing_type = 'cash_flow'
        ORDER BY ticker, period_end DESC
    """)
    income_sql = text("""
        SELECT ticker, period_end,
               payload ->> 'epsDiluted'               AS eps_diluted,
               payload ->> 'epsBasic'                 AS eps_basic,
               payload ->> 'revenue'                  AS revenue,
               payload ->> 'grossProfit'              AS gross_profit,
               payload ->> 'operatingIncome'          AS operating_income,
               payload ->> 'period'                   AS period,
               payload ->> 'form'                     AS form,
               payload ->> 'fp'                       AS fp,
               payload ->> 'weightedAverageShsOut'    AS shares_basic,
               payload ->> 'weightedAverageShsOutDil' AS shares_diluted,
               payload ->> 'marketCap'                AS market_cap_inc
        FROM fundamentals
        WHERE ticker = ANY(:t) AND filing_type = 'income'
        ORDER BY ticker, period_end DESC
    """)
    balance_sql = text("""
        SELECT DISTINCT ON (ticker)
               ticker,
               payload ->> 'totalDebt'                AS total_debt,
               payload ->> 'longTermDebt'             AS long_term_debt,
               payload ->> 'shortTermDebt'            AS short_term_debt,
               payload ->> 'totalStockholdersEquity'  AS equity
        FROM fundamentals
        WHERE ticker = ANY(:t) AND filing_type = 'balance'
        ORDER BY ticker, period_end DESC
    """)
    with session_scope() as session:
        cash_rows = session.execute(cash_sql, {"t": tickers}).all()
        inc_rows = session.execute(income_sql, {"t": tickers}).all()
        bal_rows = session.execute(balance_sql, {"t": tickers}).all()

    # Group cash rows by ticker, keep top 8 — covers:
    #   - 4 rows for the Shape-B quarterly sum
    #   - 6+ rows for the Shape-C cumulative-YTD detector
    #   - 8 rows to guarantee a prior-FY YTD anchor (~12 months back)
    #     for the precise TTM decomposition in
    #     `_decompose_cumulative_ytd_to_ttm`.
    #
    # IMPORTANT: filter rows whose freeCashFlow is null BEFORE capping.
    # Some tickers (e.g. UNH) have alternating real + restatement/erratum
    # filings where the restatement row carries no FCF value. Counting
    # those toward the cap pushes the 12-month anchor row off the end of
    # the window and degrades TTM decomposition to the max() fallback.
    cash_by_ticker: dict[str, list[dict]] = {}
    ccy_by_ticker: dict[str, str | None] = {}
    mcap_payload: dict[str, float | None] = {}
    for r in cash_rows:
        fcf = _to_float(r.fcf)
        if fcf is None:
            # Still update currency / payload-mcap from the row even if
            # FCF is missing — both fields are independent of FCF.
            if r.ticker not in ccy_by_ticker:
                ccy_by_ticker[r.ticker] = (r.ccy or "USD")
            if r.ticker not in mcap_payload and r.market_cap is not None:
                mcap_payload[r.ticker] = _to_float(r.market_cap)
            continue
        bucket = cash_by_ticker.setdefault(r.ticker, [])
        if len(bucket) < 8:
            bucket.append({
                "freeCashFlow": fcf,
                "period":       r.period,
                "period_end":   r.period_end,
            })
        # Lock in currency from the newest available row
        if r.ticker not in ccy_by_ticker:
            ccy_by_ticker[r.ticker] = (r.ccy or "USD")
        # First-seen marketCap from cash_flow
        if r.ticker not in mcap_payload and r.market_cap is not None:
            mcap_payload[r.ticker] = _to_float(r.market_cap)

    income_by_ticker: dict[str, list[dict]] = {}
    shares_by_ticker: dict[str, dict] = {}
    for r in inc_rows:
        bucket = income_by_ticker.setdefault(r.ticker, [])
        if len(bucket) < 8:
            bucket.append({
                "period_end":      r.period_end,
                "epsDiluted":      _to_float(r.eps_diluted),
                "epsBasic":        _to_float(r.eps_basic),
                "revenue":         _to_float(r.revenue),
                "grossProfit":     _to_float(r.gross_profit),
                "operatingIncome": _to_float(r.operating_income),
                "period":          r.period,
                "form":            r.form,
                "fp":              r.fp,
            })
        if r.ticker not in shares_by_ticker:
            shares_basic = _to_float(r.shares_basic)
            shares_diluted = _to_float(r.shares_diluted)
            market_cap_inc = _to_float(r.market_cap_inc)
            if shares_basic is not None or shares_diluted is not None or market_cap_inc is not None:
                shares_by_ticker[r.ticker] = {
                    "shares_basic":        shares_basic,
                    "shares_diluted":      shares_diluted,
                    "payload_mcap_income": market_cap_inc,
                }

    balance_by_ticker = {
        r.ticker: {
            "total_debt":     _to_float(r.total_debt),
            "long_term_debt": _to_float(r.long_term_debt),
            "short_term_debt": _to_float(r.short_term_debt),
            "equity":         _to_float(r.equity),
        }
        for r in bal_rows
    }

    out: dict[str, dict] = {}
    tickers_seen = set(cash_by_ticker) | set(income_by_ticker) | set(balance_by_ticker)
    for ticker in tickers_seen:
        shares = shares_by_ticker.get(ticker, {})
        out[ticker] = {
            "cash_rows":           cash_by_ticker.get(ticker, []),
            "income_rows":         income_by_ticker.get(ticker, []),
            "balance":             balance_by_ticker.get(ticker, {}),
            "reported_currency":   ccy_by_ticker.get(ticker, "USD"),
            "shares_basic":        shares.get("shares_basic"),
            "shares_diluted":      shares.get("shares_diluted"),
            "payload_mcap_cash":   mcap_payload.get(ticker),
            "payload_mcap_income": shares.get("payload_mcap_income"),
        }
    return out


def _load_latest_closes(tickers: list[str]) -> dict[str, tuple[date, float]]:
    """Most recent (ts.date(), close) per ticker."""
    sql = text("""
        SELECT DISTINCT ON (ticker) ticker, ts, close
        FROM ohlcv_1d
        WHERE ticker = ANY(:t)
        ORDER BY ticker, ts DESC
    """)
    with session_scope() as session:
        rows = session.execute(sql, {"t": tickers}).all()
    return {r.ticker: (r.ts, float(r.close)) for r in rows}


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _upsert_fundamental_features(per_ticker: dict[str, dict]) -> int:
    """Write fundamental features onto the latest existing ticker_features row.

    Why "latest existing": price features write a row per trading day. We
    treat fundamentals as point-in-time-as-of-now (they only refresh
    quarterly). The LLM prompt reads the latest row per ticker, so this is
    where it'll see fcf_yield.

    Falls back to inserting today's row keyed on the latest close ts if
    no features row exists yet for that ticker.
    """
    if not per_ticker:
        return 0
    sql = text("""
        INSERT INTO ticker_features (
            ticker, ts,
            fcf_yield, peg, market_cap_usd, operating_margin, eps_cagr_3y,
            debt_to_equity, gross_margin, gross_margin_trend
        )
        VALUES (
            :ticker, :ts,
            :fcf_yield, :peg, :market_cap_usd, :operating_margin, :eps_cagr_3y,
            :debt_to_equity, :gross_margin, :gross_margin_trend
        )
        ON CONFLICT (ticker, ts) DO UPDATE SET
            fcf_yield          = COALESCE(EXCLUDED.fcf_yield, ticker_features.fcf_yield),
            peg                = COALESCE(EXCLUDED.peg, ticker_features.peg),
            market_cap_usd     = COALESCE(EXCLUDED.market_cap_usd, ticker_features.market_cap_usd),
            operating_margin   = COALESCE(
                EXCLUDED.operating_margin, ticker_features.operating_margin
            ),
            eps_cagr_3y        = COALESCE(EXCLUDED.eps_cagr_3y, ticker_features.eps_cagr_3y),
            debt_to_equity     = COALESCE(EXCLUDED.debt_to_equity, ticker_features.debt_to_equity),
            gross_margin       = COALESCE(EXCLUDED.gross_margin, ticker_features.gross_margin),
            gross_margin_trend = COALESCE(
                EXCLUDED.gross_margin_trend, ticker_features.gross_margin_trend
            )
    """)
    written = 0
    with session_scope() as session:
        for ticker, fields in per_ticker.items():
            ts = fields.get("ts")
            if ts is None:
                continue
            session.execute(sql, {
                "ticker":             ticker,
                "ts":                 ts,
                "fcf_yield":          _f(fields.get("fcf_yield")),
                "peg":                _f(fields.get("peg")),
                "market_cap_usd":     _int_or_none(fields.get("market_cap_usd")),
                "operating_margin":   _f(fields.get("operating_margin")),
                "eps_cagr_3y":        _f(fields.get("eps_cagr_3y")),
                "debt_to_equity":     _f(fields.get("debt_to_equity")),
                "gross_margin":       _f(fields.get("gross_margin")),
                "gross_margin_trend": _f(fields.get("gross_margin_trend")),
            })
            written += 1
    return written


def build(
    tickers: list[str],
    *,
    with_fundamentals: bool = True,
) -> FeatureResult:
    """Recompute features for the given tickers from current ohlcv_1d state.

    `with_fundamentals`:
      True  (default) — also run the fundamentals pass: TTM FCF + ADR-
                        adjusted, FX-converted, freshly-priced market
                        cap → today's fcf_yield onto the latest ticker
                        row. Costs zero external API calls (all SQL).
      False           — price features only. Useful for: backtest replays
                        where fundamentals shouldn't move, debug sessions,
                        or any future cadence split where the fundamentals
                        pass runs on a different cron.
    """
    started = datetime.now()
    log.info("features.build.start", n_tickers=len(tickers),
             with_fundamentals=with_fundamentals)

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

    # ── Fundamentals pass — idempotent, no external API calls ──
    fund_written = 0
    if with_fundamentals:
        fund_per_ticker = _load_fundamentals_latest(tickers)
        closes = _load_latest_closes(tickers)
        fund_rows: dict[str, dict] = {}
        for ticker in tickers:
            f = fund_per_ticker.get(ticker)
            c = closes.get(ticker)
            if not f or not c:
                continue
            ts, close = c
            ttm_fcf = sum_ttm_fcf(f["cash_rows"])
            mcap = estimate_market_cap(
                close=close,
                shares_basic=f.get("shares_basic"),
                shares_diluted=f.get("shares_diluted"),
                payload_mcap_cash=f.get("payload_mcap_cash"),
                payload_mcap_income=f.get("payload_mcap_income"),
                ticker=ticker,
            )
            yld = compute_fcf_yield(
                close=close,
                fcf_local=ttm_fcf,
                shares_basic=f.get("shares_basic"),
                shares_diluted=f.get("shares_diluted"),
                reported_currency=f.get("reported_currency"),
                payload_mcap_cash=f.get("payload_mcap_cash"),
                payload_mcap_income=f.get("payload_mcap_income"),
                ticker=ticker,
            )
            income_rows = f.get("income_rows", [])
            annual_income = _annual_income_rows(income_rows)
            latest_income = (
                annual_income[0]
                if annual_income
                else (income_rows[0] if income_rows else {})
            )
            eps_cagr = compute_eps_cagr_3y(income_rows)
            peg = compute_peg(close, _eps_value(latest_income), eps_cagr)
            revenue = _to_float(latest_income.get("revenue"))
            gross_margin = compute_gross_margin(
                revenue,
                _to_float(latest_income.get("grossProfit")),
            )
            operating_margin = compute_gross_margin(
                revenue,
                _to_float(latest_income.get("operatingIncome")),
            )
            gross_margin_trend = compute_gross_margin_trend(income_rows)
            balance = f.get("balance", {})
            debt_to_equity = compute_debt_to_equity(
                total_debt=balance.get("total_debt"),
                long_term_debt=balance.get("long_term_debt"),
                short_term_debt=balance.get("short_term_debt"),
                equity=balance.get("equity"),
            )
            fields = {
                "ts": ts,
                "fcf_yield": yld,
                "market_cap_usd": mcap,
                "eps_cagr_3y": eps_cagr,
                "peg": peg,
                "debt_to_equity": debt_to_equity,
                "gross_margin": gross_margin,
                "gross_margin_trend": gross_margin_trend,
                "operating_margin": operating_margin,
            }
            if not any(v is not None for k, v in fields.items() if k != "ts"):
                continue
            fund_rows[ticker] = fields
        fund_written = _upsert_fundamental_features(fund_rows)
        log.info("features.fundamentals.done", tickers_with_fund_features=len(fund_rows),
                 rows_written=fund_written)

    all_ts = []
    for df_t in frames.values():
        all_ts.extend(df_t.index.tolist())
    date_range = (
        (min(all_ts).date(), max(all_ts).date()) if all_ts else None
    )

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = FeatureResult(
        tickers=sorted(frames.keys()),
        rows_written=written + fund_written,
        date_range=date_range,
        duration_ms=duration_ms,
    )
    log.info("features.build.done", rows=written + fund_written,
             ms=duration_ms, n_tickers=len(frames))
    return result

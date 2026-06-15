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

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger
from tessera_worker.universe import META_BY_TICKER

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
# ─────────────────────────────────────────────────────────────────────────
# Dual-class / multi-class equities: the "right" market cap aggregates ALL
# share classes, not just the one our ticker happens to track. yfinance /
# FMP / EDGAR all report the *company*-level marketCap on their `payload`
# fields, while `close × diluted_shares` only captures the share class
# associated with the listed ticker.
#
# GOOGL is the canonical case: $323 × 6.7B Class-A diluted ≈ $2.16T, but
# Alphabet's actual company mcap (Class A + Class B + Class C) is ~$4.4T.
# Without an override, cross_validated() logs a 2.06× disagreement warning
# on every build — noise that hides real problems.
#
# Rule: for tickers listed here, trust the payload-reported mcap (the
# "company-level" number) over the close-based candidates. We still log
# at debug level so operators can audit the path was taken; the warning
# stream stays quiet for healthy runs.
# ─────────────────────────────────────────────────────────────────────────
MULTI_CLASS_TICKERS: set[str] = {
    "GOOGL",  # Alphabet — Class A listed; Class B (non-traded) + Class C also exist
    # Add tickers here only after verifying their close × diluted gives a
    # *smaller* mcap than the canonical company-level reported value.
    # BRK.B is dual class but its diluted share count from FMP is already
    # the A-equivalent total, so it works correctly via the standard path.
}


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
    # numpy → pd.Series chain; cast keeps the public signature.
    log_ret = pd.Series(np.log(close / close.shift(1)))
    out: pd.Series = log_ret.rolling(window).std(ddof=1) * np.sqrt(
        TRADING_DAYS_PER_YEAR,
    )
    return out


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


@dataclass(frozen=True, slots=True)
class DisagreementEvent:
    """One cross-source disagreement audit event. Persisted to
    `cross_source_disagreements` so a Grafana panel can surface systemic
    cases (see PR6). Pure data — no DB."""
    feature: str                          # log_label, e.g. 'market_cap'
    ticker: str | None
    spread: float                         # max/min of candidate values
    decision: str                         # 'max' | 'min' | 'first'
    candidates: list[McapCandidate]


def cross_validated(
    candidates: list[McapCandidate],
    *,
    max_spread: float = 2.0,
    pick_on_disagreement: str = "max",
    log_label: str = "cross_validated",
    ticker: str | None = None,
    event_sink: list[DisagreementEvent] | None = None,
) -> float | None:
    """Reusable cross-validation. Used here for mcap; applies cleanly to
    any quant ratio where multiple data sources should agree.

    When `event_sink` is provided, disagreements are appended as
    DisagreementEvent records for the caller to persist (Grafana audit
    panel). The log line is emitted either way."""
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
        if event_sink is not None:
            event_sink.append(DisagreementEvent(
                feature=log_label, ticker=ticker,
                spread=round(spread, 3), decision=pick_on_disagreement,
                candidates=list(valid),
            ))
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
    event_sink: list[DisagreementEvent] | None = None,
) -> float | None:
    """Best-effort USD market cap from 4 candidates with cross-validation.

    Ordering reflects trust priority (used when candidates agree):
      1. close × shares_diluted (most-current price × inclusive share count)
      2. close × shares_basic
      3. payload_mcap_cash    (stale-by-a-quarter but a real reported number)
      4. payload_mcap_income
    """
    # Multi-class tickers: bypass cross_validated entirely. The close-
    # based candidates only see one share class and will systematically
    # disagree with the payload-reported company-level mcap. See
    # MULTI_CLASS_TICKERS docstring above.
    if ticker and ticker in MULTI_CLASS_TICKERS:
        for label, val in (
            ("payload_income", payload_mcap_income),
            ("payload_cash",   payload_mcap_cash),
        ):
            if val is not None and val > 0:
                log.debug("features.market_cap.multi_class_override",
                          ticker=ticker, label=label, value=val)
                return float(val)
        # No payload mcap available — fall through to the standard path
        # but it'll under-report. Worth a warning so we know to fix.
        log.warning("features.market_cap.multi_class_no_payload",
                    ticker=ticker,
                    hint="MULTI_CLASS_TICKERS entry exists but no payload mcap available")

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
        log_label="market_cap", ticker=ticker, event_sink=event_sink,
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


def compute_fcf_yield_normalized(
    cash_rows: list[dict[str, Any]],
    *,
    mcap: float | None,
    reported_currency: str | None = "USD",
    ticker: str | None = None,
    max_years: int = 5,
) -> float | None:
    """Normalized FCF yield: median of last `max_years` fiscal-year annual
    FCFs (USD-converted) divided by current market cap.

    Parallel to `compute_fcf_yield` (trailing TTM) — addresses cases where
    a single-year event distorts the trailing yield. UNH was the canonical
    trigger (CS-13 closing paragraph in docs/case-studies.md): 2024
    cyber-attack recovery payments shifted FCF timing, inflating trailing
    GAAP TTM vs the steady-state. Median over 5y is the simplest smoother
    that's robust to one outlier per direction without throwing away
    information.

    Returns None when:
      - fewer than 3 annual rows available (median of <3 ≈ latest value,
        no improvement over fcf_yield),
      - mcap is missing / non-positive,
      - currency is unknown,
      - result outside ±FCF_YIELD_SANITY_BOUND (same envelope as
        trailing).

    Sign convention: same as fcf_yield. Persona prompt should disclose
    BOTH (trailing GAAP + normalized) when they diverge meaningfully;
    `prompt_assembler.render_features` does that automatically when both
    columns are present.
    """
    if mcap is None or mcap <= 0:
        return None
    ccy = (reported_currency or "USD").upper()
    fx = FX_TO_USD.get(ccy)
    if fx is None:
        return None

    annuals = _annual_income_rows(cash_rows)[:max_years]
    fcf_values = [_fcf_value(r) for r in annuals]
    fcfs_usd = [float(v) * fx for v in fcf_values if v is not None]
    if len(fcfs_usd) < 3:
        return None

    fcfs_sorted = sorted(fcfs_usd)
    n = len(fcfs_sorted)
    median = (
        fcfs_sorted[n // 2]
        if n % 2 == 1
        else (fcfs_sorted[n // 2 - 1] + fcfs_sorted[n // 2]) / 2.0
    )

    yld = median / mcap
    if abs(yld) > FCF_YIELD_SANITY_BOUND:
        log.warning(
            "features.fcf_yield_normalized.sanity_drop",
            ticker=ticker, median_fcf=median, market_cap=mcap, computed=yld,
            n_years=len(fcfs_usd),
        )
        return None
    return yld


def compute_eps_cagr_3y(rows: list[dict[str, Any]]) -> float | None:
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

    cagr = float((latest_eps / anchor_eps) ** (1.0 / years) - 1.0)
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


def compute_gross_margin_trend(rows: list[dict[str, Any]]) -> float | None:
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


def _quarterly_income_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest-first income rows that look quarterly (not FY/Q4 annual).

    Quarterly cadence rows from FMP carry `period` in ('Q1','Q2','Q3').
    Q4 is treated as FY (already covered by annual). Rows without an
    explicit period label are excluded — annual math is safer as None
    than as quarterly accidentally annualized."""
    out: list[dict[str, Any]] = []
    for row in rows:
        period = (row.get("period") or "").upper()
        if period in ("Q1", "Q2", "Q3"):
            out.append(row)
    out.sort(key=lambda r: r.get("period_end") or date.min, reverse=True)
    return out


def compute_gross_margin_qtr_yoy_chg(rows: list[dict[str, Any]]) -> float | None:
    """Latest quarterly gross margin minus the same quarter of the prior
    fiscal year (Plan §5 Phase D carry-over, PR9).

    Returns None when:
      - fewer than 5 quarterly rows are present (need Q_latest + Q_yoy),
      - latest quarter is missing revenue / grossProfit,
      - no row found ~365 days before latest_pe (±45-day tolerance — same
        bound `_decompose_cumulative_ytd_to_ttm` uses for prior-YTD),
      - either margin computation falls outside the standard sanity bound.

    Sign convention: positive = margin expanded YoY, negative = compressed.
    """
    quarterly = _quarterly_income_rows(rows)
    if len(quarterly) < 5:
        return None

    latest = quarterly[0]
    latest_pe = latest.get("period_end")
    if latest_pe is None:
        return None
    latest_margin = compute_gross_margin(
        _to_float(latest.get("revenue")),
        _to_float(latest.get("grossProfit")),
    )
    if latest_margin is None:
        return None

    anchor = None
    for row in quarterly[1:]:
        pe = row.get("period_end")
        if pe is None:
            continue
        delta_days = (latest_pe - pe).days
        if 320 <= delta_days <= 410:
            anchor = row
            break
    if anchor is None:
        return None

    anchor_margin = compute_gross_margin(
        _to_float(anchor.get("revenue")),
        _to_float(anchor.get("grossProfit")),
    )
    if anchor_margin is None:
        return None
    return latest_margin - anchor_margin


FCF_STALENESS_MAX_DAYS = 400  # ~13 months — generous past the longest
# fiscal-year reporting lag (10-K usually lands within 75 days of FY-end,
# 10-Q within 40; missing every form for >13 months means the source
# isn't covering this issuer in the standard concept set).


def sum_ttm_fcf(
    rows: list[dict[str, Any]],
    *,
    fy_end_month: int | None = None,
    as_of: date | None = None,
) -> float | None:
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

    When `as_of` is provided, also returns None if the newest non-null
    FCF row is older than FCF_STALENESS_MAX_DAYS — guards against the
    COIN-style case where EDGAR concept mapping breaks for an issuer
    and the loader falls back to ancient max() of a 2-3yr-old window.
    Better N/A than a misleading number.
    """
    if not rows:
        return None

    # Staleness guard. The newest row with a non-null FCF must be within
    # FCF_STALENESS_MAX_DAYS of `as_of`. COIN was the trigger: EDGAR's
    # standard freeCashFlow concept stopped resolving for COIN after
    # 2023-09 → loader fell back to a $4B max() from a 2-3yr stale row.
    if as_of is not None:
        newest_with_fcf: date | None = None
        for r in rows:
            if _fcf_value(r) is None:
                continue
            pe = r.get("period_end")
            if pe is not None:
                newest_with_fcf = pe
                break
        if newest_with_fcf is not None:
            age = (as_of - newest_with_fcf).days
            if age > FCF_STALENESS_MAX_DAYS:
                log.warning("features.fcf_yield.stale_fundamentals",
                            newest_fcf_period=str(newest_with_fcf),
                            age_days=age,
                            limit_days=FCF_STALENESS_MAX_DAYS)
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
        # _fcf_value is not-None for every row in window (filter above);
        # tighten the list type so mypy doesn't see float|None here.
        vals: list[float] = [
            v for v in (_fcf_value(r) for r in window) if v is not None
        ]
        if len(window) >= 4:
            pos = [v for v in vals if v > 0]
            # Threshold 2.0: cumulative shape has max ≈ 4×Q1 ≈ 4×min;
            # genuinely quarterly stays within ~1.5×.
            if len(pos) >= 4 and (max(pos) / min(pos)) > 2.0:
                # (C-precise) Try period_end-aware decomposition.
                ttm = _decompose_cumulative_ytd_to_ttm(
                    window, fy_end_month=fy_end_month,
                )
                if ttm is not None:
                    return ttm
                # (C-fallback) Last fiscal-year annual ≈ TTM.
                return max(vals)

        # Shape (A-implicit): no period labels, no cumulative pattern,
        # but rows are spaced ~12 months apart → an annual-only stream
        # (FMP's older annual endpoints sometimes omit the `period` key
        # entirely). Treat rows[0] as TTM-equivalent. Seen on V's
        # cash_flow history where the latest filing has period=None
        # and the next-older is ~365d away.
        dated = [r for r in window if r.get("period_end") is not None]
        if len(dated) >= 2:
            dated.sort(key=lambda r: r["period_end"], reverse=True)
            gap_days = (dated[0]["period_end"] - dated[1]["period_end"]).days
            if 270 <= gap_days <= 410:
                v0 = _fcf_value(dated[0])
                if v0 is not None:
                    return v0

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


def _fcf_value(r: dict[str, Any]) -> float | None:
    v = r.get("freeCashFlow")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _eps_value(r: dict[str, Any]) -> float | None:
    diluted = _to_float(r.get("epsDiluted"))
    if diluted is not None:
        return diluted
    return _to_float(r.get("epsBasic"))


def _pick_latest(
    rows: list[dict[str, Any]],
    extract: Callable[[dict[str, Any]], Any],
) -> Any:
    """Return the first non-None value yielded by `extract(row)` walking
    `rows` newest-first. Used so a partial latest filing can fall back
    to an older row that actually carries the field we need."""
    for r in rows:
        v = extract(r)
        if v is not None:
            return v
    return None


def _annual_income_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _decompose_cumulative_ytd_to_ttm(
    rows: list[dict[str, Any]],
    *,
    fy_end_month: int | None = None,
) -> float | None:
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

    When `fy_end_month` is provided (e.g. AAPL=9, COST=8, AMZN=12), the
    anchor lookup uses month-match instead of a ±45-day day-delta:
      - prior_ytd = row with same month as latest_pe, one year earlier
      - last_fy_annual = row whose month == fy_end_month, between them

    This rescues UNH / AMZN / COIN cases where the prior-year same-
    quarter row is exactly ~365 days away but the day-delta window
    misses by a few days (53-week fiscal years, restated filings),
    silently falling back to max(window) = last full FY (up to 12 months
    stale, Plan §5 line 734).

    Falls back to the original day-delta heuristic when fy_end_month is
    not provided or month-match returns no candidates.

    Returns None when any of:
      - period_end missing on every candidate row,
      - no row found 1 year before the latest (month-match or ±45 days),
      - no FY annual candidate found between prior YTD and current YTD,
      - universe is too sparse to do TTM decomposition.
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

    # Find prior YTD anchor — month-match preferred (calendar-precise),
    # day-delta fallback for unknown FY months.
    prior_ytd_row = None
    prior_pe = None
    if fy_end_month is not None:
        for pe, r in dated[1:]:
            if (
                pe.month == latest_pe.month
                and (latest_pe.year - pe.year) == 1
            ):
                prior_ytd_row = r
                prior_pe = pe
                break
    if prior_ytd_row is None:
        # Fallback: ±45-day window around 365 days (handles 5-week
        # month variance + occasional 53-week fiscal years).
        for pe, r in dated[1:]:
            delta_days = (latest_pe - pe).days
            if 320 <= delta_days <= 410:
                prior_ytd_row = r
                prior_pe = pe
                break
    if prior_ytd_row is None or prior_pe is None:
        return None
    prior_ytd = _fcf_value(prior_ytd_row)
    if prior_ytd is None:
        return None

    # The "last full FY" annual lives strictly between prior_pe and
    # latest_pe. Month-match (period_end.month == fy_end_month) is more
    # precise than max-value when there are duplicate / restated rows,
    # but the max-value heuristic remains the safe fallback because it
    # only relies on the cumulative-YTD invariant (Q4 = FY annual = the
    # largest cumulative value of any quarter).
    last_fy_annual: float | None = None
    if fy_end_month is not None:
        for pe, r in dated:
            if pe <= prior_pe or pe >= latest_pe:
                continue
            if pe.month == fy_end_month:
                v = _fcf_value(r)
                if v is not None:
                    last_fy_annual = v
                    break
    if last_fy_annual is None:
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
    """Return tidy DataFrame: index=(ticker, ts), columns=open/high/low/close/volume.

    One row per (ticker, calendar day). The PK is (ticker, ts) with ts
    TIMESTAMPTZ, and mixed-source history stored the same calendar day under
    different ts values (Alpaca 04:00Z vs the Yahoo backfill's 00:00Z). Every
    feature below is a row-window computation (ret_30d = 30 rows, vol_30d,
    rsi_14, sma_*, volume_z), so duplicate days silently halve the effective
    horizon wherever two sources overlap. Migration 006 deleted the existing
    duplicates; the DISTINCT ON here is defense in depth against any future
    multi-source backfill re-introducing them.

    Source preference mirrors 006: the daily-cron feeds (alpaca, coinbase)
    win over backfill (yahoo), so the recent window always matches what the
    nightly ingest writes.
    """
    sql = text("""
        SELECT DISTINCT ON (ticker, ts::date)
               ticker, ts, open, high, low, close, volume
        FROM ohlcv_1d
        WHERE ticker = ANY(:tickers)
        ORDER BY ticker, ts::date,
                 CASE source
                     WHEN 'alpaca'   THEN 1
                     WHEN 'coinbase' THEN 1
                     WHEN 'yahoo'    THEN 2
                     ELSE 3
                 END,
                 ts DESC
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
    rows: list[dict[str, Any]] = []
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


def _f(v: Any) -> float | None:
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


def _int_or_none(v: Any) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


# ─────────────────────────────────────────────────────────────────────────
# Fundamentals loader + latest-row upsert
# ─────────────────────────────────────────────────────────────────────────

def _load_fundamentals_latest(tickers: list[str]) -> dict[str, dict[str, Any]]:
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
               payload ->> 'form'             AS form,
               payload ->> 'fp'               AS fp,
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
               payload ->> 'marketCap'                AS market_cap_inc,
               -- Yahoo-derived fallbacks (only populated on synthetic
               -- rows written by yf_shares ingestor). compute uses these
               -- when EDGAR-derived versions are None — see build().
               payload ->> 'peg_yf'                   AS peg_yf,
               payload ->> 'gross_margin_yf'          AS gross_margin_yf,
               payload ->> 'pe_trailing_yf'           AS pe_trailing_yf,
               payload ->> 'pe_forward_yf'            AS pe_forward_yf
        FROM fundamentals
        WHERE ticker = ANY(:t) AND filing_type = 'income'
        ORDER BY ticker, period_end DESC
    """)
    # NOTE: we deliberately do NOT use `DISTINCT ON (ticker)` here. FMP
    # occasionally writes a preliminary balance row where every field
    # we care about is null (seen on V's 2026-03-31 filing). With
    # DISTINCT ON we'd lock in that empty row and ship NULL forever.
    # Instead we pull all balance rows newest-first and walk per field
    # below, so equity from an older row can rescue a stale debt entry.
    balance_sql = text("""
        SELECT ticker, period_end,
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
    cash_by_ticker: dict[str, list[dict[str, Any]]] = {}
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
        # Cap 24 (was 8): sum_ttm_fcf self-limits to the newest 8 rows, but
        # compute_fcf_yield_normalized needs ~5 ANNUAL FY rows — for a
        # quarterly filer that's up to 20 quarterly rows back. 24 covers
        # 5+ fiscal years of mixed cadence. Carry form/fp so the annual
        # filter (`_annual_income_rows`) can recognize EDGAR cash_flow rows
        # (period is often NULL on EDGAR-sourced rows; form='10-K'/fp='FY'
        # is how they mark annual). Without these the normalized median
        # silently returned None for all EDGAR-only tickers (#134 follow-up).
        if len(bucket) < 24:
            bucket.append({
                "freeCashFlow": fcf,
                "period":       r.period,
                "form":         r.form,
                "fp":           r.fp,
                "period_end":   r.period_end,
            })
        # Lock in currency from the newest available row
        if r.ticker not in ccy_by_ticker:
            ccy_by_ticker[r.ticker] = (r.ccy or "USD")
        # First-seen marketCap from cash_flow
        if r.ticker not in mcap_payload and r.market_cap is not None:
            mcap_payload[r.ticker] = _to_float(r.market_cap)

    income_by_ticker: dict[str, list[dict[str, Any]]] = {}
    shares_by_ticker: dict[str, dict[str, Any]] = {}
    # Income cap raised from 8 → 24 so we always carry at least 4 annual
    # rows for filers that mix quarterly + annual in the same table.
    # V is the canonical case: 8-row window holds 6 quarters + 2 FY rows,
    # so `_annual_income_rows` returns only 2 and `compute_eps_cagr_3y`
    # bails on `len(annual) < 4`. With 24 we cover 4 fiscal years of
    # quarterly+annual reliably.
    for r in inc_rows:
        bucket = income_by_ticker.setdefault(r.ticker, [])
        if len(bucket) < 24:
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
        # Per-field newest-non-null fall-through. FMP often returns a
        # preliminary income row where shares/marketCap are null even
        # though the filing is real (V 2026-03-31 is the canonical
        # case). We walk newest-first and fill each field independently
        # from the first row where that field is non-null. Mixing fields
        # across rows is fine: shares_basic from FY2025 + market_cap
        # from cash_flow today is still a coherent mcap estimate.
        bucket_shares = shares_by_ticker.setdefault(r.ticker, {
            "shares_basic":        None,
            "shares_diluted":      None,
            "payload_mcap_income": None,
            "peg_yf":              None,
            "gross_margin_yf":     None,
            "pe_trailing_yf":      None,
            "pe_forward_yf":       None,
        })
        if bucket_shares["shares_basic"] is None:
            bucket_shares["shares_basic"] = _to_float(r.shares_basic)
        if bucket_shares["shares_diluted"] is None:
            bucket_shares["shares_diluted"] = _to_float(r.shares_diluted)
        if bucket_shares["payload_mcap_income"] is None:
            bucket_shares["payload_mcap_income"] = _to_float(r.market_cap_inc)
        if bucket_shares["peg_yf"] is None:
            bucket_shares["peg_yf"] = _to_float(r.peg_yf)
        if bucket_shares["gross_margin_yf"] is None:
            bucket_shares["gross_margin_yf"] = _to_float(r.gross_margin_yf)
        if bucket_shares["pe_trailing_yf"] is None:
            bucket_shares["pe_trailing_yf"] = _to_float(r.pe_trailing_yf)
        if bucket_shares["pe_forward_yf"] is None:
            bucket_shares["pe_forward_yf"] = _to_float(r.pe_forward_yf)

    # Same fall-through pattern for balance: pick the freshest non-null
    # value per field across all available balance filings.
    balance_by_ticker: dict[str, dict[str, Any]] = {}
    for r in bal_rows:
        b = balance_by_ticker.setdefault(r.ticker, {
            "total_debt":      None,
            "long_term_debt":  None,
            "short_term_debt": None,
            "equity":          None,
        })
        if b["total_debt"] is None:
            b["total_debt"] = _to_float(r.total_debt)
        if b["long_term_debt"] is None:
            b["long_term_debt"] = _to_float(r.long_term_debt)
        if b["short_term_debt"] is None:
            b["short_term_debt"] = _to_float(r.short_term_debt)
        if b["equity"] is None:
            b["equity"] = _to_float(r.equity)

    out: dict[str, dict[str, Any]] = {}
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
            "peg_yf":              shares.get("peg_yf"),
            "gross_margin_yf":     shares.get("gross_margin_yf"),
            "pe_trailing_yf":      shares.get("pe_trailing_yf"),
            "pe_forward_yf":       shares.get("pe_forward_yf"),
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


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _persist_disagreements(events: list[DisagreementEvent]) -> None:
    """Insert one row per disagreement into `cross_source_disagreements`.

    Audit log feeding the Grafana panel; the warning log already fired
    inside `cross_validated` so this is purely for slow-pace aggregation
    (which tickers are systemic, how the spread evolves over time)."""
    if not events:
        return
    import json as _json
    rows = [
        {
            "feature":    e.feature,
            "ticker":     e.ticker,
            "spread":     e.spread,
            "decision":   e.decision,
            "candidates": _json.dumps(
                [{"label": lbl, "value": v} for lbl, v in e.candidates],
            ),
        }
        for e in events
    ]
    sql = text("""
        INSERT INTO cross_source_disagreements
            (feature, ticker, spread, decision, candidates)
        VALUES (:feature, :ticker, :spread, :decision,
                CAST(:candidates AS jsonb))
    """)
    with session_scope() as session:
        session.execute(sql, rows)


def _upsert_fundamental_features(per_ticker: dict[str, dict[str, Any]]) -> int:
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
            fcf_yield, fcf_yield_normalized, peg, market_cap_usd,
            operating_margin, eps_cagr_3y, debt_to_equity, gross_margin,
            gross_margin_trend, gross_margin_qtr_yoy_chg,
            pe_trailing, pe_forward
        )
        VALUES (
            :ticker, :ts,
            :fcf_yield, :fcf_yield_normalized, :peg, :market_cap_usd,
            :operating_margin, :eps_cagr_3y, :debt_to_equity, :gross_margin,
            :gross_margin_trend, :gross_margin_qtr_yoy_chg,
            :pe_trailing, :pe_forward
        )
        ON CONFLICT (ticker, ts) DO UPDATE SET
            fcf_yield          = COALESCE(EXCLUDED.fcf_yield, ticker_features.fcf_yield),
            fcf_yield_normalized = COALESCE(
                EXCLUDED.fcf_yield_normalized, ticker_features.fcf_yield_normalized
            ),
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
            ),
            gross_margin_qtr_yoy_chg = COALESCE(
                EXCLUDED.gross_margin_qtr_yoy_chg,
                ticker_features.gross_margin_qtr_yoy_chg
            ),
            pe_trailing        = COALESCE(EXCLUDED.pe_trailing, ticker_features.pe_trailing),
            pe_forward         = COALESCE(EXCLUDED.pe_forward, ticker_features.pe_forward)
    """)
    written = 0
    with session_scope() as session:
        for ticker, fields in per_ticker.items():
            ts = fields.get("ts")
            if ts is None:
                continue
            session.execute(sql, {
                "ticker":               ticker,
                "ts":                   ts,
                "fcf_yield":            _f(fields.get("fcf_yield")),
                "fcf_yield_normalized": _f(fields.get("fcf_yield_normalized")),
                "peg":                  _f(fields.get("peg")),
                "market_cap_usd":       _int_or_none(fields.get("market_cap_usd")),
                "operating_margin":     _f(fields.get("operating_margin")),
                "eps_cagr_3y":          _f(fields.get("eps_cagr_3y")),
                "debt_to_equity":       _f(fields.get("debt_to_equity")),
                "gross_margin":         _f(fields.get("gross_margin")),
                "gross_margin_trend":   _f(fields.get("gross_margin_trend")),
                "gross_margin_qtr_yoy_chg": _f(fields.get("gross_margin_qtr_yoy_chg")),
                "pe_trailing":          _f(fields.get("pe_trailing")),
                "pe_forward":           _f(fields.get("pe_forward")),
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
        # MultiIndex .loc[ticker] returns DataFrame for our (ticker, ts)
        # layout — single-row tickers would surface as Series and we'd
        # already have skipped them via the index check above.
        df_t = df.loc[ticker].sort_index()
        assert isinstance(df_t, pd.DataFrame)
        frames[ticker] = _compute_for_ticker(df_t)

    written = _upsert_features(frames)

    # ── Fundamentals pass — idempotent, no external API calls ──
    fund_written = 0
    if with_fundamentals:
        fund_per_ticker = _load_fundamentals_latest(tickers)
        closes = _load_latest_closes(tickers)
        fund_rows: dict[str, dict[str, Any]] = {}
        # Collect cross-source disagreement events per build run; persisted
        # at the end into `cross_source_disagreements` (Grafana audit panel
        # source).
        disagreement_events: list[DisagreementEvent] = []
        for ticker in tickers:
            f = fund_per_ticker.get(ticker)
            c = closes.get(ticker)
            if not f or not c:
                continue
            ts, close = c
            meta = META_BY_TICKER.get(ticker)
            fy_end_month = meta.fy_end_month if meta is not None else None
            # ts may be a datetime (TIMESTAMPTZ → psycopg returns
            # datetime) or a date — normalise to date for the guard.
            as_of_date = ts.date() if isinstance(ts, datetime) else ts
            ttm_fcf = sum_ttm_fcf(
                f["cash_rows"], fy_end_month=fy_end_month,
                as_of=as_of_date,
            )
            mcap = estimate_market_cap(
                close=close,
                shares_basic=f.get("shares_basic"),
                shares_diluted=f.get("shares_diluted"),
                payload_mcap_cash=f.get("payload_mcap_cash"),
                payload_mcap_income=f.get("payload_mcap_income"),
                ticker=ticker,
                event_sink=disagreement_events,
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
            yld_normalized = compute_fcf_yield_normalized(
                f["cash_rows"], mcap=mcap,
                reported_currency=f.get("reported_currency"),
                ticker=ticker,
            )
            income_rows = f.get("income_rows", [])
            annual_income = _annual_income_rows(income_rows)
            # Pull each margin / EPS input from the newest annual row
            # where that specific field is non-null. FMP preliminary
            # rows (e.g. V 2026-03-31) zero out grossProfit/EPS while
            # keeping revenue + operatingIncome; using annual[0] for
            # everything blanks the whole quality column. See
            # _load_fundamentals_latest for the loader-side fix.
            search_rows = annual_income or income_rows
            latest_eps = _pick_latest(search_rows, _eps_value)
            latest_revenue = _pick_latest(
                search_rows, lambda r: _to_float(r.get("revenue"))
            )
            latest_gross_profit = _pick_latest(
                search_rows, lambda r: _to_float(r.get("grossProfit"))
            )
            latest_operating_income = _pick_latest(
                search_rows, lambda r: _to_float(r.get("operatingIncome"))
            )
            eps_cagr = compute_eps_cagr_3y(income_rows)
            peg = compute_peg(close, latest_eps, eps_cagr)
            gross_margin = compute_gross_margin(latest_revenue, latest_gross_profit)
            operating_margin = compute_gross_margin(
                latest_revenue, latest_operating_income
            )
            # yfinance-derived fallbacks: only used when our EDGAR-driven
            # computation came up None. Service / payment-network filers
            # (V, MA) genuinely don't tag GrossProfit in XBRL, and have
            # no historical EPS series we can hit for trailing PEG, so
            # Yahoo's pre-computed ratios are the only path to a number.
            # Sanity-bound to the same envelope as our own outputs so a
            # yf glitch can't ship a 500% margin into the LLM prompt.
            if peg is None:
                yf_peg = f.get("peg_yf")
                if yf_peg is not None and 0 < yf_peg < PEG_SANITY_BOUND:
                    peg = yf_peg
            if gross_margin is None:
                yf_gm = f.get("gross_margin_yf")
                if yf_gm is not None and MARGIN_SANITY_LOW <= yf_gm <= MARGIN_SANITY_HIGH:
                    gross_margin = yf_gm
            # P/E: try close / latest_eps first (EDGAR-driven path), then
            # yfinance trailingPE as fallback. Sanity-bound at 500 to drop
            # the occasional restatement/transition quarter outlier
            # (Yahoo sometimes shows 4000+ for newly-listed names).
            pe_trailing = None
            if close is not None and latest_eps is not None and latest_eps > 0:
                candidate = close / latest_eps
                if 0 < candidate < 500:
                    pe_trailing = candidate
            if pe_trailing is None:
                yf_pe = f.get("pe_trailing_yf")
                if yf_pe is not None and 0 < yf_pe < 500:
                    pe_trailing = yf_pe
            pe_forward = None
            yf_pe_fwd = f.get("pe_forward_yf")
            if yf_pe_fwd is not None and 0 < yf_pe_fwd < 500:
                pe_forward = yf_pe_fwd
            gross_margin_trend = compute_gross_margin_trend(income_rows)
            gross_margin_qtr_yoy_chg = compute_gross_margin_qtr_yoy_chg(
                income_rows,
            )
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
                "fcf_yield_normalized": yld_normalized,
                "market_cap_usd": mcap,
                "eps_cagr_3y": eps_cagr,
                "peg": peg,
                "debt_to_equity": debt_to_equity,
                "gross_margin": gross_margin,
                "gross_margin_trend": gross_margin_trend,
                "gross_margin_qtr_yoy_chg": gross_margin_qtr_yoy_chg,
                "operating_margin": operating_margin,
                "pe_trailing": pe_trailing,
                "pe_forward": pe_forward,
            }
            if not any(v is not None for k, v in fields.items() if k != "ts"):
                continue
            fund_rows[ticker] = fields
        fund_written = _upsert_fundamental_features(fund_rows)
        log.info("features.fundamentals.done", tickers_with_fund_features=len(fund_rows),
                 rows_written=fund_written)
        if disagreement_events:
            _persist_disagreements(disagreement_events)
            log.info("features.disagreements.persisted",
                     n=len(disagreement_events))

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

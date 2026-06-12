"""Paper execution engine — turns persisted books into a paper P&L track.

Deterministic Python only, no LLM. Runs as the `paper` step at the END of
the daily orchestrator (after features + canary), gated on
`FEATURE_PAPER_EXECUTION`. Three phases per persona, all idempotent:

  1. REBALANCE (fills at the open) — if the persona's latest non-rejected
     book (analyst_reports, MAX(as_of_date)) has not been executed yet
     (no persona_trades row carries its report_id), diff target weights
     against current positions and fill the difference at each ticker's
     most-recent bar OPEN. The weekly batch runs Friday 22:00 UTC after
     the Friday ingest, so the first ingest that sees the new book is
     Monday's — fills land at Monday's open, which is exactly the
     "fill at next-day open" rule from Plan.md §5. Fractional shares
     allowed (paper); no commissions or slippage modelled in v1.
  2. MARK-TO-MARKET — value positions at each ticker's most-recent bar
     CLOSE, write one persona_portfolios snapshot per calendar day
     (PK (persona_id, ts) with ts = the day at midnight UTC → re-runs
     upsert instead of duplicating).
  3. PERFORMANCE — upsert today's persona_performance row: pnl_day /
     pnl_cum / return_day / return_cum vs the $100K paper start,
     sharpe_30d from the trailing return_day series, mdd_30d from the
     trailing total_value series.

Bootstrap: a persona with no persona_portfolios row starts at
INITIAL_CAPITAL_USD all-cash; its first executed book buys in from cash.

NAV conservation is exact by construction: `compute_rebalance` repays
every dollar of sells into cash and funds every buy from it, so
cash + Σ(qty × price) before == after. The unit tests pin this.

Ray's RegimeReport books (instrument-keyed `allocations`) execute through
the same path as stock-picker `proposals` — both reduce to
{ticker: target_weight}.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

INITIAL_CAPITAL_USD = 100_000.0
# Ignore dust rebalances — a $1 order on a $100K book is float noise, and
# skipping it keeps the trade ledger readable.
MIN_TRADE_USD = 1.0
# A position whose newest bar is older than this is logged loudly — its
# valuation is stale (delisted ticker, ingest gap). Crypto trades weekends
# so equities are the ones that age over holidays; 7 days is generous.
STALE_PRICE_DAYS = 7

PERSONAS: tuple[str, ...] = ("warren", "cathie", "ray", "peter")


# ─────────────────────────────────────────────────────────────────────────
# Pure functions — all the math, no DB. Unit-tested directly.
# ─────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PaperFill:
    ticker: str
    side: str          # 'buy' | 'sell'
    qty: float         # always positive; side carries direction
    price: float       # fill price (bar open)

    @property
    def value(self) -> float:
        return self.qty * self.price


def compute_rebalance(
    positions: dict[str, float],
    cash: float,
    targets: dict[str, float],
    prices: dict[str, float],
    *,
    min_trade_usd: float = MIN_TRADE_USD,
) -> tuple[list[PaperFill], dict[str, float], float]:
    """Diff current holdings against target weights at the given prices.

    positions: ticker → qty currently held.
    targets:   ticker → target fraction of NAV (cash is the implied rest).
    prices:    ticker → fill price. MUST cover every ticker in
               positions ∪ targets — the caller filters/falls back first.

    Returns (fills, new_positions, new_cash). NAV is conserved exactly:
    new_cash + Σ(new_qty × price) == cash + Σ(qty × price).
    """
    nav = cash + sum(qty * prices[t] for t, qty in positions.items())
    fills: list[PaperFill] = []
    new_positions = dict(positions)

    for ticker in sorted(set(positions) | set(targets)):
        price = prices[ticker]
        if price <= 0:
            continue  # defensive: a zero/negative bar is corrupt data
        current_qty = positions.get(ticker, 0.0)
        target_qty = (targets.get(ticker, 0.0) * nav) / price
        diff_qty = target_qty - current_qty
        if abs(diff_qty) * price < min_trade_usd:
            continue
        fills.append(PaperFill(
            ticker=ticker,
            side="buy" if diff_qty > 0 else "sell",
            qty=abs(diff_qty),
            price=price,
        ))
        new_positions[ticker] = target_qty

    # Drop closed/never-opened slots; keep float dust out of the book.
    new_positions = {t: q for t, q in new_positions.items() if q > 1e-9}
    new_cash = nav - sum(q * prices[t] for t, q in new_positions.items())
    return fills, new_positions, new_cash


def mark_to_market(
    positions: dict[str, float], cash: float, closes: dict[str, float],
) -> float:
    """Total portfolio value at the given closes. Missing closes raise —
    the caller guarantees coverage (a held ticker always has the bar its
    fill came from)."""
    return cash + sum(qty * closes[t] for t, qty in positions.items())


def sharpe_30d(daily_returns: list[float]) -> float | None:
    """Annualized Sharpe over the trailing daily-return series (risk-free
    rate 0 for the pilot). None until we have 5 observations — a 2-day
    Sharpe is noise wearing a suit."""
    rets = [r for r in daily_returns if r is not None][-30:]
    if len(rets) < 5:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    std = math.sqrt(var)
    if std < 1e-12:
        return None
    return (mean / std) * math.sqrt(252)


def max_drawdown(values: list[float]) -> float | None:
    """Max peak-to-trough drawdown (as a positive fraction) over the
    series. None with fewer than 2 points."""
    vals = [v for v in values if v is not None][-30:]
    if len(vals) < 2:
        return None
    peak = vals[0]
    mdd = 0.0
    for v in vals:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd


def book_to_targets(parsed: dict[str, Any]) -> dict[str, float]:
    """Reduce a persisted book (stock-picker `proposals` or Ray's
    `allocations`) to {ticker: weight>0}. Cash is the implied remainder —
    the engine never needs cash_target explicitly because NAV − positions
    IS cash after the rebalance."""
    targets: dict[str, float] = {}
    for p in (parsed.get("proposals") or []):
        ticker = p.get("ticker")
        weight = float(p.get("target_weight") or 0.0)
        if ticker and weight > 0:
            targets[ticker] = weight
    for a in (parsed.get("allocations") or []):
        instrument = a.get("instrument")
        weight = float(a.get("target_weight") or 0.0)
        if instrument and weight > 0:
            targets[instrument] = weight
    return targets


# ─────────────────────────────────────────────────────────────────────────
# DB shell
# ─────────────────────────────────────────────────────────────────────────

def _load_latest_book(
    session: Session, persona: str,
) -> tuple[str, date, dict[str, Any]] | None:
    """(report_id, as_of_date, parsed) for the persona's current book —
    latest batch day only (same scoping rule as /api/proposals; older
    batch days must never leak positions into execution)."""
    row = session.execute(text("""
        SELECT id::text AS id, as_of_date, parsed
        FROM analyst_reports
        WHERE persona_id = :p AND rejected = false
          AND as_of_date = (
              SELECT MAX(as_of_date) FROM analyst_reports
              WHERE persona_id = :p AND rejected = false
          )
        ORDER BY ts DESC
        LIMIT 1
    """), {"p": persona}).first()
    if not row:
        return None
    parsed = row.parsed if isinstance(row.parsed, dict) else {}
    return row.id, row.as_of_date, parsed


def _book_already_executed(session: Session, persona: str, report_id: str) -> bool:
    row = session.execute(text("""
        SELECT 1 FROM persona_trades
        WHERE persona_id = :p AND report_id = :rid
        LIMIT 1
    """), {"p": persona, "rid": report_id}).first()
    return row is not None


def _load_portfolio(session: Session, persona: str) -> tuple[dict[str, float], float]:
    """(positions {ticker: qty}, cash) from the latest snapshot, or the
    all-cash bootstrap if the persona has never traded."""
    row = session.execute(text("""
        SELECT positions, cash
        FROM persona_portfolios
        WHERE persona_id = :p
        ORDER BY ts DESC
        LIMIT 1
    """), {"p": persona}).first()
    if not row:
        return {}, INITIAL_CAPITAL_USD
    raw = row.positions if isinstance(row.positions, dict) else {}
    positions = {
        t: float(v["qty"]) for t, v in raw.items()
        if isinstance(v, dict) and float(v.get("qty") or 0) > 0
    }
    return positions, float(row.cash)


def _load_latest_bars(
    session: Session, tickers: set[str],
) -> dict[str, tuple[date, float, float]]:
    """ticker → (bar_date, open, close) from each ticker's most-recent
    bar. Post-006 there is one row per calendar day, so DISTINCT ON
    (ticker) is canonical."""
    if not tickers:
        return {}
    rows = session.execute(text("""
        SELECT DISTINCT ON (ticker) ticker, ts::date AS d, open, close
        FROM ohlcv_1d
        WHERE ticker = ANY(:t)
        ORDER BY ticker, ts DESC
    """), {"t": sorted(tickers)}).all()
    out: dict[str, tuple[date, float, float]] = {}
    for r in rows:
        if r.open is None or r.close is None:
            continue
        out[r.ticker] = (r.d, float(r.open), float(r.close))
    return out


def _run_persona(session: Session, persona: str, today: date) -> dict[str, Any]:
    """Rebalance-if-needed + MTM + performance for one persona. Returns
    step-detail fields for the orchestrator log line."""
    positions, cash = _load_portfolio(session, persona)
    book = _load_latest_book(session, persona)

    fills: list[PaperFill] = []
    executed_report: str | None = None

    if book is not None:
        report_id, book_date, parsed = book
        if not _book_already_executed(session, persona, report_id):
            targets = book_to_targets(parsed)
            bars = _load_latest_bars(session, set(positions) | set(targets))

            # Targets without a price can't be filled — their weight stays
            # in cash until data arrives. A HELD ticker without a price is
            # worse (can't value the book): freeze and skip the rebalance.
            unpriced_targets = sorted(set(targets) - set(bars))
            if unpriced_targets:
                log.warning("paper_engine.targets_unpriced",
                            persona=persona, tickers=unpriced_targets)
                targets = {t: w for t, w in targets.items() if t in bars}
            unpriced_held = sorted(set(positions) - set(bars))
            if unpriced_held:
                log.error("paper_engine.held_position_unpriced",
                          persona=persona, tickers=unpriced_held,
                          hint="rebalance skipped — cannot value the book")
            else:
                opens = {t: b[1] for t, b in bars.items()}
                stale = sorted(
                    t for t, b in bars.items()
                    if (today - b[0]).days > STALE_PRICE_DAYS
                    and (t in targets or t in positions)
                )
                if stale:
                    log.warning("paper_engine.stale_prices",
                                persona=persona, tickers=stale)
                fills, positions, cash = compute_rebalance(
                    positions, cash, targets, opens,
                )
                for f in fills:
                    session.execute(text("""
                        INSERT INTO persona_trades
                            (persona_id, ticker, side, qty, price,
                             report_id, rationale_md, mode)
                        VALUES (:p, :t, :side, :qty, :price,
                                CAST(:rid AS uuid), :why, 'paper')
                    """), {
                        "p": persona, "t": f.ticker, "side": f.side,
                        "qty": round(f.qty, 6), "price": round(f.price, 6),
                        "rid": report_id,
                        "why": (f"rebalance to book {book_date.isoformat()} "
                                f"(target {targets.get(f.ticker, 0.0):.2%})"),
                    })
                executed_report = report_id
                log.info("paper_engine.rebalanced",
                         persona=persona, book=book_date.isoformat(),
                         n_fills=len(fills),
                         traded_usd=round(sum(f.value for f in fills), 2))

    # ── Mark-to-market + snapshot (runs daily even with no rebalance) ──
    bars = _load_latest_bars(session, set(positions))
    missing = sorted(set(positions) - set(bars))
    if missing:
        log.error("paper_engine.mtm_skipped_unpriced",
                  persona=persona, tickers=missing)
        # A held position we can't price means the persona's NAV is
        # frozen/unknown — page-worthy even though we degrade gracefully.
        import sentry_sdk
        sentry_sdk.capture_message(
            f"paper_engine: {persona} MTM skipped — held positions "
            f"unpriced: {missing}", level="error",
        )
        return {"persona": persona, "fills": len(fills), "mtm": "skipped"}
    closes = {t: b[2] for t, b in bars.items()}
    total_value = mark_to_market(positions, cash, closes)

    positions_jsonb = {
        t: {"qty": round(q, 6), "close": closes[t],
            "value": round(q * closes[t], 2)}
        for t, q in positions.items()
    }
    import json as _json
    session.execute(text("""
        INSERT INTO persona_portfolios (persona_id, ts, cash, positions, total_value)
        VALUES (:p, CAST(:d AS timestamptz), :cash, CAST(:pos AS jsonb), :tv)
        ON CONFLICT (persona_id, ts) DO UPDATE SET
            cash = EXCLUDED.cash,
            positions = EXCLUDED.positions,
            total_value = EXCLUDED.total_value
    """), {"p": persona, "d": today.isoformat(), "cash": round(cash, 2),
           "pos": _json.dumps(positions_jsonb), "tv": round(total_value, 2)})

    # ── Performance row ────────────────────────────────────────────────
    prev = session.execute(text("""
        SELECT total_value FROM persona_portfolios
        WHERE persona_id = :p AND ts < CAST(:d AS timestamptz)
        ORDER BY ts DESC LIMIT 1
    """), {"p": persona, "d": today.isoformat()}).first()
    prev_value = float(prev.total_value) if prev else INITIAL_CAPITAL_USD

    pnl_day = total_value - prev_value
    return_day = (pnl_day / prev_value) if prev_value > 0 else 0.0
    pnl_cum = total_value - INITIAL_CAPITAL_USD
    return_cum = total_value / INITIAL_CAPITAL_USD - 1.0

    ret_rows = session.execute(text("""
        SELECT return_day FROM persona_performance
        WHERE persona_id = :p AND date < :d
        ORDER BY date DESC LIMIT 29
    """), {"p": persona, "d": today}).all()
    returns = [float(r.return_day) for r in reversed(ret_rows)
               if r.return_day is not None] + [return_day]

    val_rows = session.execute(text("""
        SELECT total_value FROM persona_portfolios
        WHERE persona_id = :p AND ts <= CAST(:d AS timestamptz)
        ORDER BY ts DESC LIMIT 30
    """), {"p": persona, "d": today.isoformat()}).all()
    values = [float(r.total_value) for r in reversed(val_rows)]

    session.execute(text("""
        INSERT INTO persona_performance
            (persona_id, date, pnl_day, pnl_cum, return_day, return_cum,
             sharpe_30d, mdd_30d, trades_count)
        VALUES (:p, :d, :pd, :pc, :rd, :rc, :sharpe, :mdd, :n)
        ON CONFLICT (persona_id, date) DO UPDATE SET
            pnl_day = EXCLUDED.pnl_day,
            pnl_cum = EXCLUDED.pnl_cum,
            return_day = EXCLUDED.return_day,
            return_cum = EXCLUDED.return_cum,
            sharpe_30d = EXCLUDED.sharpe_30d,
            mdd_30d = EXCLUDED.mdd_30d,
            trades_count = EXCLUDED.trades_count
    """), {
        "p": persona, "d": today,
        "pd": round(pnl_day, 2), "pc": round(pnl_cum, 2),
        "rd": round(return_day, 4), "rc": round(return_cum, 4),
        "sharpe": sharpe_30d(returns), "mdd": max_drawdown(values),
        "n": len(fills),
    })

    return {
        "persona": persona,
        "fills": len(fills),
        "executed_report": executed_report,
        "total_value": round(total_value, 2),
        "cash": round(cash, 2),
        "n_positions": len(positions),
    }


def run_paper_engine(as_of: date | None = None) -> dict[str, Any]:
    """Run all three phases for every persona. Per-persona errors are
    caught and counted — one persona's bad day must not block the
    others' mark-to-market."""
    today = as_of or date.today()
    results: list[dict[str, Any]] = []
    errors = 0
    for persona in PERSONAS:
        try:
            with session_scope() as session:
                results.append(_run_persona(session, persona, today))
        except Exception as e:
            errors += 1
            log.error("paper_engine.persona_failed",
                      persona=persona, err=f"{type(e).__name__}: {e}")
            # Per-persona isolation swallows the exception so the other
            # books still mark-to-market — but that also hid it from
            # Sentry's unhandled-exception capture. Page explicitly:
            # a persona whose ledger stops updating is a Sev-2 (Plan §9
            # "paper engine error → page within 5 min").
            import sentry_sdk
            sentry_sdk.capture_exception(e)
    total_fills = sum(r.get("fills", 0) for r in results)
    log.info("paper_engine.done", date=str(today),
             personas=len(results), errors=errors, fills=total_fills)
    return {
        "personas": len(results),
        "errors": errors,
        "fills": total_fills,
        "books": {r["persona"]: r.get("total_value") for r in results},
    }

"""Frozen-book paper-history backfill — one-shot operator job.

Gives the performance chart ~1 year of history by answering exactly one
question: **"what would each persona's CURRENT holdings have been worth,
held unchanged, over the past year?"** (decision 2026-06-12 — cheap and
deterministic, vs a point-in-time backtest replay at ~$30–70 of LLM).

What it does, per persona:
  1. Reads the FIRST REAL persona_portfolios snapshot (the engine's
     bootstrap day) and freezes its exact quantities + cash. Because the
     hypothetical path is the real holdings valued backwards in time, the
     last backfilled day flows into the first real day with no seam —
     continuity is by construction, no scaling fudge.
  2. Walks the equity trading calendar (SPY bar dates) from `--years` ago
     up to (not including) the real track's first day, valuing the frozen
     book at each day's closes. Tickers without a bar that day (crypto
     trades weekends, half-days, listing gaps) carry their last known
     close forward; days before a ticker ever traded are skipped at the
     head of the series so the book is always fully priced.
  3. Writes persona_portfolios + persona_performance rows with
     **hypothetical = true** (migration 007). pnl/return are measured
     from the first hypothetical day; sharpe_30d / mdd_30d use the same
     math as the live engine. trades_count is always 0 — no fake fills,
     and persona_trades is never touched.

Honesty contract: this history has **look-ahead bias** — the book was
constructed with 2026 knowledge, so a year of it held "backwards" is
flattering by selection. That is why every row is flagged and why the UI
must label the segment ("Hypothetical — current book held 1y"). The real
track accumulating from 2026-06-11 onward is the honest record.

Safety: upserts can never touch a real row — writes are restricted to
days strictly before the real track's first snapshot AND the ON CONFLICT
update applies only `WHERE ... hypothetical = true`. Re-running is
idempotent (recomputes and overwrites the hypothetical segment only).

Run (operator, after applying migrations/007):
    python -m tessera_worker.jobs.backfill_paper_history --dry-run
    python -m tessera_worker.jobs.backfill_paper_history
    python -m tessera_worker.jobs.backfill_paper_history --years 1 --personas warren ray
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.db import session_scope
from tessera_worker.logging import configure_logging, get_logger
from tessera_worker.risk.paper_engine import PERSONAS, max_drawdown, sharpe_30d

configure_logging()
log = get_logger(__name__)

DEFAULT_YEARS = 1
# Look this many days before the requested start for each ticker's first
# close, so forward-fill has a seed even when the start lands mid-gap.
FFILL_GRACE_DAYS = 14


# ─────────────────────────────────────────────────────────────────────────
# Pure core — unit-tested without a DB
# ─────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class DayValue:
    day: date
    total_value: float
    position_values: dict[str, tuple[float, float]]  # ticker -> (close, value)


def build_value_series(
    calendar: list[date],
    closes: dict[str, dict[date, float]],
    positions: dict[str, float],
    cash: float,
) -> list[DayValue]:
    """Value the frozen book on each calendar day with per-ticker
    forward-fill.

    `closes[ticker]` may contain dates outside `calendar` (the grace
    window, crypto weekends) — they seed/refresh the forward-fill but
    only calendar days produce output rows. Leading calendar days where
    any held ticker has no known close yet are skipped: a partially
    priced book would understate value and poison return_cum from day
    one.
    """
    if not positions:
        return [DayValue(d, cash, {}) for d in calendar]

    last_close: dict[str, float] = {}
    # Pre-sort each ticker's quote dates once; walk with an index so the
    # whole series builds in O(days + quotes).
    quote_dates = {t: sorted(closes.get(t, {})) for t in positions}
    cursor = dict.fromkeys(positions, 0)

    out: list[DayValue] = []
    for day in sorted(calendar):
        for ticker in positions:
            dates = quote_dates[ticker]
            i = cursor[ticker]
            while i < len(dates) and dates[i] <= day:
                last_close[ticker] = closes[ticker][dates[i]]
                i += 1
            cursor[ticker] = i
        if len(last_close) < len(positions):
            continue  # head of series: some ticker hasn't traded yet
        position_values = {
            t: (last_close[t], qty * last_close[t])
            for t, qty in positions.items()
        }
        total = cash + sum(v for _, v in position_values.values())
        out.append(DayValue(day, total, position_values))
    return out


@dataclass(frozen=True, slots=True)
class PerfRow:
    day: date
    pnl_day: float
    pnl_cum: float
    return_day: float
    return_cum: float
    sharpe: float | None
    mdd: float | None


def build_performance_rows(series: list[DayValue]) -> list[PerfRow]:
    """Daily performance vs the FIRST hypothetical day (the segment's own
    baseline — not the $100K bootstrap, which belongs to the real track)."""
    rows: list[PerfRow] = []
    if not series:
        return rows
    base = series[0].total_value
    returns: list[float] = []
    values: list[float] = []
    prev = base
    for dv in series:
        pnl_day = dv.total_value - prev
        return_day = (pnl_day / prev) if prev > 0 else 0.0
        returns.append(return_day)
        values.append(dv.total_value)
        rows.append(PerfRow(
            day=dv.day,
            pnl_day=pnl_day,
            pnl_cum=dv.total_value - base,
            return_day=return_day,
            return_cum=(dv.total_value / base - 1.0) if base > 0 else 0.0,
            sharpe=sharpe_30d(returns[-30:]),
            mdd=max_drawdown(values[-30:]),
        ))
        prev = dv.total_value
    return rows


# ─────────────────────────────────────────────────────────────────────────
# DB shell
# ─────────────────────────────────────────────────────────────────────────

def _first_real_snapshot(
    session: Session, persona: str,
) -> tuple[date, dict[str, float], float] | None:
    """(day, positions {ticker: qty}, cash) of the persona's earliest
    REAL snapshot — the frozen book and the backfill's exclusive upper
    bound."""
    row = session.execute(text("""
        SELECT ts::date AS d, positions, cash
        FROM persona_portfolios
        WHERE persona_id = :p AND NOT hypothetical
        ORDER BY ts ASC
        LIMIT 1
    """), {"p": persona}).first()
    if not row:
        return None
    raw = row.positions if isinstance(row.positions, dict) else {}
    positions = {
        t: float(v["qty"]) for t, v in raw.items()
        if isinstance(v, dict) and float(v.get("qty") or 0) > 0
    }
    return row.d, positions, float(row.cash)


def _equity_calendar(session: Session, start: date, end_excl: date) -> list[date]:
    rows = session.execute(text("""
        SELECT DISTINCT ts::date AS d
        FROM ohlcv_1d
        WHERE ticker = 'SPY' AND ts::date >= :s AND ts::date < :e
        ORDER BY d
    """), {"s": start, "e": end_excl}).all()
    return [r.d for r in rows]


def _load_closes(
    session: Session, tickers: set[str], start: date, end_excl: date,
) -> dict[str, dict[date, float]]:
    if not tickers:
        return {}
    rows = session.execute(text("""
        SELECT ticker, ts::date AS d, close
        FROM ohlcv_1d
        WHERE ticker = ANY(:t)
          AND ts::date >= :s AND ts::date < :e
          AND close IS NOT NULL
        ORDER BY ticker, d
    """), {"t": sorted(tickers), "s": start - timedelta(days=FFILL_GRACE_DAYS),
           "e": end_excl}).all()
    out: dict[str, dict[date, float]] = {}
    for r in rows:
        out.setdefault(r.ticker, {})[r.d] = float(r.close)
    return out


def _write_segment(
    session: Session,
    persona: str,
    series: list[DayValue],
    perf: list[PerfRow],
    positions: dict[str, float],
    cash: float,
) -> int:
    """Upsert the hypothetical segment. The `WHERE ... hypothetical`
    guard on both DO UPDATEs makes overwriting a real row impossible even
    if date math ever regresses."""
    snap_sql = text("""
        INSERT INTO persona_portfolios
            (persona_id, ts, cash, positions, total_value, hypothetical)
        VALUES (:p, CAST(:d AS timestamptz), :cash, CAST(:pos AS jsonb), :tv, true)
        ON CONFLICT (persona_id, ts) DO UPDATE SET
            cash = EXCLUDED.cash,
            positions = EXCLUDED.positions,
            total_value = EXCLUDED.total_value,
            hypothetical = true
        WHERE persona_portfolios.hypothetical
    """)
    perf_sql = text("""
        INSERT INTO persona_performance
            (persona_id, date, pnl_day, pnl_cum, return_day, return_cum,
             sharpe_30d, mdd_30d, trades_count, hypothetical)
        VALUES (:p, :d, :pd, :pc, :rd, :rc, :sharpe, :mdd, 0, true)
        ON CONFLICT (persona_id, date) DO UPDATE SET
            pnl_day = EXCLUDED.pnl_day,
            pnl_cum = EXCLUDED.pnl_cum,
            return_day = EXCLUDED.return_day,
            return_cum = EXCLUDED.return_cum,
            sharpe_30d = EXCLUDED.sharpe_30d,
            mdd_30d = EXCLUDED.mdd_30d,
            hypothetical = true
        WHERE persona_performance.hypothetical
    """)
    for dv, pr in zip(series, perf, strict=True):
        # qty is constant for the whole segment (frozen book) — stored on
        # every row so a snapshot is self-describing for audit.
        positions_jsonb = {
            t: {"qty": round(positions[t], 6), "close": close,
                "value": round(value, 2), "frozen": True}
            for t, (close, value) in dv.position_values.items()
        }
        session.execute(snap_sql, {
            "p": persona, "d": dv.day.isoformat(), "cash": round(cash, 2),
            "pos": json.dumps(positions_jsonb),
            "tv": round(dv.total_value, 2),
        })
        session.execute(perf_sql, {
            "p": persona, "d": dv.day,
            "pd": round(pr.pnl_day, 2), "pc": round(pr.pnl_cum, 2),
            "rd": round(pr.return_day, 4), "rc": round(pr.return_cum, 4),
            "sharpe": pr.sharpe, "mdd": pr.mdd,
        })
    return len(series)


def run_backfill(
    *, years: int = DEFAULT_YEARS,
    personas: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Backfill all requested personas. Returns {persona: rows_written}."""
    targets = personas or list(PERSONAS)
    written: dict[str, int] = {}
    for persona in targets:
        with session_scope() as session:
            snap = _first_real_snapshot(session, persona)
            if snap is None:
                log.warning("paper_backfill.no_real_snapshot", persona=persona,
                            hint="run the paper engine first — the frozen book "
                                 "is the first real bootstrap")
                written[persona] = 0
                continue
            seam_day, positions, cash = snap
            start = seam_day - timedelta(days=365 * years)
            calendar = _equity_calendar(session, start, seam_day)
            closes = _load_closes(session, set(positions), start, seam_day)

            never_priced = sorted(set(positions) - set(closes))
            if never_priced:
                # No data at all in the window — fold into cash so the
                # rest of the book still backfills (logged for audit).
                log.warning("paper_backfill.ticker_unpriced_dropped",
                            persona=persona, tickers=never_priced)
                positions = {t: q for t, q in positions.items()
                             if t not in never_priced}

            series = build_value_series(calendar, closes, positions, cash)
            perf = build_performance_rows(series)
            if dry_run:
                first = series[0] if series else None
                last = series[-1] if series else None
                log.info("paper_backfill.dry_run", persona=persona,
                         days=len(series),
                         start=str(first.day) if first else None,
                         start_value=round(first.total_value, 2) if first else None,
                         end=str(last.day) if last else None,
                         end_value=round(last.total_value, 2) if last else None)
                written[persona] = len(series)
                continue
            n = _write_segment(session, persona, series, perf, positions, cash)
            written[persona] = n
            log.info("paper_backfill.persona_done", persona=persona, rows=n,
                     seam=str(seam_day),
                     return_cum=(round(perf[-1].return_cum, 4) if perf else None))
    log.info("paper_backfill.done", rows=written)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Frozen-book hypothetical paper-history backfill")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS)
    parser.add_argument("--personas", nargs="+", choices=list(PERSONAS))
    parser.add_argument("--dry-run", action="store_true",
                        help="compute + log, write nothing")
    args = parser.parse_args(argv)
    written = run_backfill(years=args.years, personas=args.personas,
                           dry_run=args.dry_run)
    print("--- paper history backfill ---")
    for persona, n in written.items():
        print(f"  {persona:8} {n:>5} days{'  (dry-run)' if args.dry_run else ''}")
    return 0 if all(n > 0 for n in written.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

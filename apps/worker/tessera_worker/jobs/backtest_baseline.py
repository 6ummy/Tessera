"""90-day point-in-time backtest baseline — the credibility anchor.

The real paper track only started 2026-06-11, so per-archetype Sharpe/MDD
needs a backtest. This does the honest (look-ahead-free) version Plan §5
specifies: at each WEEKLY replay date over the window, regenerate each
persona's book using ONLY data available at that date (v2 two-pass,
persist=False so the live `analyst_reports` table is untouched), then
simulate holding each weekly book and rebalancing to the next — and read
the per-persona Sharpe/MDD off the resulting daily equity curve.

Scope (the cheap-but-honest sweet spot, decided 2026-06-13): WEEKLY
sampling × a small ticker shortlist per persona. Daily replay over 90
days would be ~$67 and ~19h; weekly × 5 tickers is ~$6 and ~1.5h.

Cost guard: every construct/research call logs to `llm_call_log` and is
subject to the global daily budget cap (`check_daily_budget`). A full
run will exceed the $5 prod cap — the operator raises
`LLM_MAX_DAILY_COST_USD` for the one-off run (see the runbook section in
the module docstring's CLI help). `--max-cost` is the harness-level cap.

Two halves, cleanly separated:
  - PURE core (no DB/LLM, unit-tested): `weekly_replay_dates`,
    `simulate_track`, `baseline_metrics`. Reuses paper_engine's
    `compute_rebalance` / `mark_to_market`.
  - SHELL (DB + LLM): `generate_books`, `load_daily_prices`,
    `run_baseline`.

Run (operator):
    # dry-run verifies the date schedule + price coverage, $0, no LLM
    python -m tessera_worker.jobs.backtest_baseline --dry-run
    # real run (bump the global cap first):
    #   gcloud run services update tessera-worker --region us-east1 \
    #       --update-env-vars LLM_MAX_DAILY_COST_USD=20
    python -m tessera_worker.jobs.backtest_baseline --weeks 13 --max-cost 15
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.agents.persona_loader import PersonaId
from tessera_worker.db import session_scope
from tessera_worker.jobs.persona_batch import PERSONA_SHORTLISTS
from tessera_worker.logging import configure_logging, get_logger
from tessera_worker.risk.paper_engine import (
    INITIAL_CAPITAL_USD,
    compute_rebalance,
    mark_to_market,
)

configure_logging()
log = get_logger(__name__)

DEFAULT_WEEKS = 13          # ~90 calendar days
DEFAULT_TICKERS_PER_PERSONA = 5
TRADING_DAYS_PER_YEAR = 252
PERSONAS: tuple[str, ...] = ("warren", "cathie", "peter", "ray")

# Representative Ray ETF book for dry-run only (no LLM available). Mirrors
# the typical regime-thesis output (broad equity + intl + duration + gold)
# so the dry-run still exercises ETF price coverage end-to-end.
_RAY_DRY_RUN_BOOK: dict[str, float] = {
    "VTI": 0.30, "VXUS": 0.15, "TLT": 0.15, "IEF": 0.15, "GLD": 0.15, "QQQ": 0.10,
}


# ─────────────────────────────────────────────────────────────────────────
# Pure core
# ─────────────────────────────────────────────────────────────────────────

def weekly_replay_dates(end: date, weeks: int) -> list[date]:
    """`weeks` weekday dates spaced 7 days apart, oldest first, ending at
    the most recent weekday on/before `end`. Weekly because the personas
    only act weekly in production — a daily replay would be redundant and
    ~5× the cost."""
    anchor = end
    while anchor.weekday() >= 5:  # back up off the weekend
        anchor -= timedelta(days=1)
    out = [anchor - timedelta(days=7 * i) for i in range(weeks)]
    return list(reversed(out))


@dataclass(frozen=True, slots=True)
class DayBar:
    open: float
    close: float


def simulate_track(
    books_by_date: dict[date, dict[str, float]],
    bars: dict[str, dict[date, DayBar]],
    calendar: list[date],
) -> list[tuple[date, float]]:
    """Walk the calendar holding the most-recent book, rebalancing to a
    new book at the open on its replay date and marking to market at the
    close every day. Returns [(day, total_value)] — the equity curve.

    Reuses paper_engine.compute_rebalance (fills at open, NAV-conserving)
    and mark_to_market (value at close). Forward-fills a ticker's last
    close when it has no bar that day (holidays / listing gaps). Days
    before the book is fully priceable are skipped at the head."""
    positions: dict[str, float] = {}
    cash = INITIAL_CAPITAL_USD
    last_close: dict[str, float] = {}
    curve: list[tuple[date, float]] = []

    for day in sorted(calendar):
        # refresh known closes (and opens) up to today
        for ticker, by_day in bars.items():
            bar = by_day.get(day)
            if bar is not None:
                last_close[ticker] = bar.close

        # rebalance at the open if a new book lands today
        if day in books_by_date:
            targets = {t: w for t, w in books_by_date[day].items() if w > 0}
            opens = {
                t: bars[t][day].open
                for t in set(targets) | set(positions)
                if t in bars and day in bars[t]
            }
            # only rebalance tickers we can price at the open today
            priceable = {t: w for t, w in targets.items() if t in opens}
            held_priceable = all(t in opens for t in positions)
            if priceable and held_priceable:
                _fills, positions, cash = compute_rebalance(
                    positions, cash, priceable, opens,
                )

        # mark to market at the close — skip until every held name prices
        if positions and any(t not in last_close for t in positions):
            continue
        closes = {t: last_close[t] for t in positions}
        curve.append((day, mark_to_market(positions, cash, closes)))

    return curve


@dataclass(frozen=True, slots=True)
class BaselineMetrics:
    days: int
    total_return: float
    annualized_sharpe: float | None
    max_drawdown: float | None  # positive fraction


def baseline_metrics(curve: list[tuple[date, float]]) -> BaselineMetrics:
    """Full-window metrics off the daily equity curve (not the paper
    engine's 30-day trailing versions — a baseline wants the whole
    period). Sharpe is annualized with rf=0; MDD is peak-to-trough over
    the entire curve."""
    if len(curve) < 2:
        return BaselineMetrics(len(curve), 0.0, None, None)
    values = [v for _, v in curve]
    rets = [values[i] / values[i - 1] - 1.0
            for i in range(1, len(values)) if values[i - 1] > 0]
    total_return = values[-1] / values[0] - 1.0 if values[0] > 0 else 0.0

    sharpe: float | None = None
    if len(rets) >= 5:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        std = math.sqrt(var)
        if std > 1e-12:
            sharpe = (mean / std) * math.sqrt(TRADING_DAYS_PER_YEAR)

    peak = values[0]
    mdd = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)

    return BaselineMetrics(len(curve), round(total_return, 4),
                           round(sharpe, 3) if sharpe is not None else None,
                           round(mdd, 4))


# ─────────────────────────────────────────────────────────────────────────
# Shell
# ─────────────────────────────────────────────────────────────────────────

# Personas whose shortlist must be passed in full regardless of the
# `--tickers-per-persona` flag, because the construction call's hard
# constraints can't be satisfied from a truncated slice. Cathie is the
# canonical case: her 14-name shortlist is 10 equities (7+ of them
# Technology) plus 4 crypto pairs that exist specifically to give the
# sector cap headroom. Truncating to the first 10 drops the crypto
# sleeve, making the 70% Tech cap mathematically violable by
# `normalize_book` alone — the 2026-06-14 baseline hit this and Cathie
# failed 6/9 cells (sector 'Technology' weight 0.79 > sector cap 0.70).
# See Plan §5 carry-over.
_FULL_SHORTLIST_PERSONAS: frozenset[str] = frozenset({"cathie"})


def _tickers_for(persona: str, n: int) -> list[str]:
    shortlist = PERSONA_SHORTLISTS.get(persona, [])
    if persona in _FULL_SHORTLIST_PERSONAS:
        return list(shortlist)
    return shortlist[:n]


@dataclass
class BaselineRun:
    cost_usd: float = 0.0
    errors: int = 0
    books: dict[str, dict[date, dict[str, float]]] = field(default_factory=dict)


def generate_books(
    replay_dates: list[date], n_tickers: int, max_cost: float,
    *, dry_run: bool, run: BaselineRun,
) -> None:
    """Point-in-time v2 books per (persona, replay date). persist=False
    everywhere — the live analyst_reports table is never written. On any
    per-cell failure the prior week's book carries forward (a real PM
    doesn't liquidate because one research call timed out)."""
    from tessera_worker.agents.anthropic_runner import (
        run_regime_thesis,
        run_research,
    )
    from tessera_worker.agents.portfolio_construction import construct_portfolio
    from tessera_worker.risk.paper_engine import book_to_targets

    for persona in PERSONAS:
        run.books.setdefault(persona, {})

    for d in replay_dates:
        if run.cost_usd >= max_cost:
            log.warning("backtest_baseline.cost_cap_hit",
                        spent=round(run.cost_usd, 2), cap=max_cost)
            return
        for persona in PERSONAS:
            tickers = _tickers_for(persona, n_tickers)
            if dry_run:
                if persona == "ray":
                    run.books[persona][d] = dict(_RAY_DRY_RUN_BOOK)
                else:
                    run.books[persona][d] = dict.fromkeys(
                        tickers, 1.0 / max(len(tickers), 1)
                    )
                continue
            try:
                if persona == "ray":
                    rep = run_regime_thesis(
                        as_of=d, persist=False,
                        cost_namespace="backtest_baseline",
                    )
                    run.cost_usd += float(rep.cost_usd)
                    run.books[persona][d] = {
                        a.instrument: a.target_weight for a in rep.allocations
                    }
                else:
                    p_id = cast(PersonaId, persona)
                    notes = []
                    for t in tickers:
                        note = run_research(
                            p_id, t, as_of=d,
                            cost_namespace="backtest_baseline",
                        )
                        if note is not None:
                            run.cost_usd += float(note.get("cost_usd", 0.0))
                            notes.append(note)
                    if not notes:
                        raise RuntimeError("no research notes")
                    report = construct_portfolio(
                        p_id, notes, as_of=d, persist=False,
                        cost_namespace="backtest_baseline",
                    )
                    run.cost_usd += float(report.cost_usd)
                    run.books[persona][d] = book_to_targets(
                        report.model_dump()
                    )
                log.info("backtest_baseline.book", persona=persona, as_of=str(d),
                         n=len(run.books[persona][d]),
                         cost=round(run.cost_usd, 2))
            except Exception as e:
                run.errors += 1
                log.warning("backtest_baseline.book_failed",
                            persona=persona, as_of=str(d), err=str(e))


def load_daily_prices(
    session: Session, tickers: set[str], start: date, end: date,
) -> dict[str, dict[date, DayBar]]:
    """Per-ticker {day: DayBar(open, close)} over [start, end], canonical
    one-row-per-day (post-006). Opens feed fills, closes feed MTM."""
    if not tickers:
        return {}
    rows = session.execute(text("""
        SELECT DISTINCT ON (ticker, ts::date)
               ticker, ts::date AS d, open, close
        FROM ohlcv_1d
        WHERE ticker = ANY(:t) AND ts::date >= :s AND ts::date <= :e
          AND open IS NOT NULL AND close IS NOT NULL
        ORDER BY ticker, ts::date,
                 CASE source WHEN 'alpaca' THEN 1 WHEN 'coinbase' THEN 1
                             WHEN 'yahoo' THEN 2 ELSE 3 END, ts DESC
    """), {"t": sorted(tickers), "s": start, "e": end}).all()
    out: dict[str, dict[date, DayBar]] = {}
    for r in rows:
        out.setdefault(r.ticker, {})[r.d] = DayBar(float(r.open), float(r.close))
    return out


def run_baseline(
    *, end: date | None = None, weeks: int = DEFAULT_WEEKS,
    n_tickers: int = DEFAULT_TICKERS_PER_PERSONA,
    dry_run: bool = False, max_cost: float = 15.0,
) -> dict[str, BaselineMetrics]:
    end = end or date.today()
    replay_dates = weekly_replay_dates(end, weeks)
    run = BaselineRun()

    all_tickers: set[str] = set()
    for persona in PERSONAS:
        all_tickers.update(_tickers_for(persona, n_tickers))

    log.info("backtest_baseline.start", weeks=weeks, n_tickers=n_tickers,
             window=f"{replay_dates[0]}->{replay_dates[-1]}",
             tickers=len(all_tickers), dry_run=dry_run)

    generate_books(replay_dates, n_tickers, max_cost, dry_run=dry_run, run=run)

    # Ray's tickers are only known after generate_books (regime thesis picks
    # the ETF set per replay date). Union them in so load_daily_prices
    # covers everything that will need pricing.
    for persona_books in run.books.values():
        for book in persona_books.values():
            all_tickers.update(book.keys())

    # Daily calendar = trading days between first replay and end.
    with session_scope() as session:
        cal_rows = session.execute(text("""
            SELECT DISTINCT ts::date AS d FROM ohlcv_1d
            WHERE ticker = 'SPY' AND ts::date >= :s AND ts::date <= :e
            ORDER BY d
        """), {"s": replay_dates[0], "e": end}).all()
        calendar = [r.d for r in cal_rows]
        bars = load_daily_prices(session, all_tickers, replay_dates[0], end)

    metrics: dict[str, BaselineMetrics] = {}
    for persona in PERSONAS:
        curve = simulate_track(run.books.get(persona, {}), bars, calendar)
        metrics[persona] = baseline_metrics(curve)

    log.info("backtest_baseline.done", cost=round(run.cost_usd, 2),
             errors=run.errors,
             metrics={p: m.annualized_sharpe for p, m in metrics.items()})
    return metrics


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="90-day point-in-time backtest baseline")
    p.add_argument("--weeks", type=int, default=DEFAULT_WEEKS)
    p.add_argument("--tickers-per-persona", type=int,
                   default=DEFAULT_TICKERS_PER_PERSONA)
    p.add_argument("--end-date", type=str, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-cost", type=float, default=15.0)
    args = p.parse_args(argv)
    end = date.fromisoformat(args.end_date) if args.end_date else date.today()

    metrics = run_baseline(end=end, weeks=args.weeks,
                           n_tickers=args.tickers_per_persona,
                           dry_run=args.dry_run, max_cost=args.max_cost)

    print("\n=== 90-day backtest baseline" + ("  (dry-run)" if args.dry_run else "") + " ===")
    print(f"  {'persona':<8} {'days':>5} {'total':>9} {'sharpe':>8} {'maxDD':>8}")
    for persona, m in metrics.items():
        tr = f"{m.total_return*100:+.2f}%"
        sh = f"{m.annualized_sharpe:.2f}" if m.annualized_sharpe is not None else "—"
        dd = f"{m.max_drawdown*100:.2f}%" if m.max_drawdown is not None else "—"
        print(f"  {persona:<8} {m.days:>5} {tr:>9} {sh:>8} {dd:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

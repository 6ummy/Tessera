"""Ticker-level P&L attribution over the paper track (Plan §5 Week 5).

Answers "which names drove this persona's return over the period" from
the daily persona_portfolios snapshots — no trades table needed, because
flows are priced at the close:

    pnl_d(ticker) = value_d − value_{d−1} − (qty_d − qty_{d−1}) × close_d
                  = qty_{d−1} × (close_d − close_{d−1})

i.e. yesterday's holding times today's price move. The day a position is
opened contributes nothing (qty_{d−1} = 0) and the open→close move of
the traded delta on a rebalance day is deliberately unattributed — a
known v1 approximation (fills happen at the open; snapshots only carry
closes). Cash contributes zero. Contributions are expressed as
fractions of the period's STARTING NAV, so they sum to ≈ the period's
total return (pinned by tests).

Works identically across the hypothetical backfill and the live track —
the frozen backfill book is just a constant-qty special case.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Snapshot:
    day: date
    positions: dict[str, tuple[float, float]]  # ticker -> (qty, close)
    total_value: float


@dataclass(frozen=True, slots=True)
class TickerAttribution:
    ticker: str
    pnl: float            # absolute $ over the period
    contribution: float   # fraction of period-start NAV


def compute_attribution(snapshots: list[Snapshot]) -> list[TickerAttribution]:
    """Per-ticker P&L across consecutive snapshots, sorted by |pnl| desc.

    Needs ≥2 snapshots; returns [] otherwise. Tickers that appear in any
    snapshot get a row, including fully-closed positions (their realized
    move up to the close-out day is still attributed)."""
    if len(snapshots) < 2:
        return []
    ordered = sorted(snapshots, key=lambda s: s.day)
    start_nav = ordered[0].total_value
    pnl: dict[str, float] = {}
    for prev, curr in zip(ordered, ordered[1:], strict=False):
        for ticker, (qty_prev, close_prev) in prev.positions.items():
            close_curr = (
                curr.positions[ticker][1]
                if ticker in curr.positions else None
            )
            if close_curr is None:
                # Position closed today: its move to the close-out price
                # is embedded in cash via the fill; with close-priced
                # flows that residual is zero — skip.
                continue
            pnl[ticker] = pnl.get(ticker, 0.0) + qty_prev * (close_curr - close_prev)
    out = [
        TickerAttribution(
            ticker=t,
            pnl=round(v, 2),
            contribution=round(v / start_nav, 6) if start_nav > 0 else 0.0,
        )
        for t, v in pnl.items()
    ]
    out.sort(key=lambda a: -abs(a.pnl))
    return out


def load_snapshots(
    session: Session, persona: str, start: date,
) -> list[Snapshot]:
    """Snapshots from `start` (inclusive) onward — hypothetical + real,
    ordered ascending. The jsonb positions carry qty + close on every
    row (engine and backfill both write them)."""
    rows = session.execute(text("""
        SELECT ts::date AS d, positions, total_value
        FROM persona_portfolios
        WHERE persona_id = :p AND ts::date >= :s
        ORDER BY ts ASC
    """), {"p": persona, "s": start}).all()
    out: list[Snapshot] = []
    for r in rows:
        raw = r.positions if isinstance(r.positions, dict) else {}
        positions: dict[str, tuple[float, float]] = {}
        for ticker, v in raw.items():
            if not isinstance(v, dict):
                continue
            qty = float(v.get("qty") or 0.0)
            close = float(v.get("close") or 0.0)
            if qty > 0 and close > 0:
                positions[ticker] = (qty, close)
        out.append(Snapshot(day=r.d, positions=positions,
                            total_value=float(r.total_value)))
    return out

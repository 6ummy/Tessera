"""Mirror engine — project each persona's paper book onto its followers.

Phase D. When a user follows a persona (a `user_portfolios` row seeded by
the web `/api/follow` route), this step keeps that row's positions / cash /
total_value in sync with the persona's live paper book.

# Model: weight projection, not independent fills

A follower holds the SAME target weights as the persona, scaled to the
follower's NAV, from their `started_at` forward. So:

    follower_return_since_follow == persona_return_since_follow
    follower_nav = starting_capital * (persona_nav_today / persona_nav_at_start)

We do NOT simulate per-follower fills bar-by-bar — that would mean N×M
fill simulation + per-follower slippage with no added truth (v1 has no
fees, and "you follow this persona's book" is exactly a weight mirror).
The projection is deterministic arithmetic over the persona's existing
`persona_portfolios` snapshots, so it's cheap and exactly reconciles to
the persona's published track.

`started_at` is the point-in-time anchor: a follower's baseline is the
persona's NAV on (or just before) the day they followed — no backfill,
no look-ahead. Follow today and your curve starts flat.

Runs in the nightly ingest right AFTER the persona paper engine, so
today's `persona_portfolios` snapshot is already written. Gated on the
same FEATURE_PAPER_EXECUTION flag (it's meaningless without the persona
track it projects).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger
from tessera_worker.risk.paper_engine import _load_latest_bars

log = get_logger(__name__)


def _persona_snapshot(
    session: Session, persona: str,
) -> tuple[dict[str, float], float, float] | None:
    """Latest (positions {ticker: qty}, cash, total_value) for a persona,
    or None if the persona has never been marked (no followers to mirror
    onto a non-existent book)."""
    row = session.execute(text("""
        SELECT positions, cash, total_value
        FROM persona_portfolios
        WHERE persona_id = :p
        ORDER BY ts DESC
        LIMIT 1
    """), {"p": persona}).first()
    if not row:
        return None
    raw = row.positions if isinstance(row.positions, dict) else {}
    positions = {
        t: float(v["qty"]) for t, v in raw.items()
        if isinstance(v, dict) and float(v.get("qty") or 0) > 0
    }
    return positions, float(row.cash), float(row.total_value)


def _persona_nav_at(session: Session, persona: str, started: date) -> float | None:
    """Persona NAV on the latest snapshot at or before `started` — the
    follower's baseline. Falls back to the earliest snapshot when the
    follow predates the first one (shouldn't happen: you can't follow a
    persona before it has a book)."""
    row = session.execute(text("""
        SELECT total_value FROM persona_portfolios
        WHERE persona_id = :p AND ts::date <= :d
        ORDER BY ts DESC LIMIT 1
    """), {"p": persona, "d": started.isoformat()}).first()
    if row is None:
        row = session.execute(text("""
            SELECT total_value FROM persona_portfolios
            WHERE persona_id = :p ORDER BY ts ASC LIMIT 1
        """), {"p": persona}).first()
    return float(row.total_value) if row and row.total_value is not None else None


def project_follower_book(
    persona_positions: dict[str, float],
    persona_cash: float,
    nav_today: float,
    nav_at_start: float,
    starting_capital: float,
    closes: dict[str, float],
) -> tuple[dict[str, dict[str, float]], float, float]:
    """Pure weight projection — the heart of the mirror. Given the persona's
    book today (positions in shares + cash + NAV), the persona NAV on the
    follower's start date, and the follower's starting capital, return
    (positions_jsonb, follower_cash, follower_nav).

    follower_nav = starting_capital * (nav_today / nav_at_start), so the
    follower's return since following equals the persona's over the same
    window. Holdings carry the persona's weights, scaled to that NAV.
    Tickers with no usable close are dropped (their weight implicitly falls
    to cash — surfaced by the caller's conservation, not silently lost)."""
    follower_nav = starting_capital * (nav_today / nav_at_start)
    positions_jsonb: dict[str, dict[str, float]] = {}
    for ticker, qty in persona_positions.items():
        price = closes.get(ticker)
        if not price or price <= 0:
            continue
        weight = (qty * price) / nav_today
        value = follower_nav * weight
        positions_jsonb[ticker] = {
            "qty": round(value / price, 6),
            "close": price,
            "value": round(value, 2),
        }
    follower_cash = follower_nav * (persona_cash / nav_today)
    return positions_jsonb, follower_cash, follower_nav


def _mirror_one(
    session: Session,
    follow: Any,
    snapshot: tuple[dict[str, float], float, float],
    closes: dict[str, float],
) -> bool:
    """Project the persona book onto a single follower row. Returns True
    if the row was updated."""
    positions, persona_cash, nav_today = snapshot
    if nav_today <= 0:
        return False
    base = _persona_nav_at(session, follow.persona_id, follow.started_at.date())
    if not base or base <= 0:
        return False

    positions_jsonb, follower_cash, follower_nav = project_follower_book(
        positions, persona_cash, nav_today, base, float(follow.starting_capital), closes,
    )

    session.execute(text("""
        UPDATE user_portfolios
        SET current_positions = CAST(:pos AS jsonb),
            current_cash = :cash,
            total_value = :tv
        WHERE id = :id
    """), {
        "id": str(follow.id),
        "pos": json.dumps(positions_jsonb),
        "cash": round(follower_cash, 2),
        "tv": round(follower_nav, 2),
    })
    return True


def run_mirror_engine(as_of: date | None = None) -> dict[str, Any]:
    """Sync every paper follower's positions/cash/total_value to the
    persona book they follow. Idempotent — re-running on the same day
    recomputes the same projection."""
    today = as_of or date.today()
    with session_scope() as session:
        follows = session.execute(text("""
            SELECT id, persona_id, started_at, starting_capital
            FROM user_portfolios
            WHERE mode = 'paper'
        """)).all()
        if not follows:
            log.info("mirror.no_followers")
            return {"followers": 0, "updated": 0}

        # Cache per-persona snapshot + today's closes so N followers of the
        # same persona share one set of queries.
        snap_cache: dict[str, tuple[dict[str, float], float, float] | None] = {}
        close_cache: dict[str, dict[str, float]] = {}
        updated = 0
        skipped = 0
        for f in follows:
            persona = f.persona_id
            if persona not in snap_cache:
                snap_cache[persona] = _persona_snapshot(session, persona)
                snap = snap_cache[persona]
                bars = _load_latest_bars(
                    session, set(snap[0]) if snap else set(), as_of=as_of,
                )
                close_cache[persona] = {t: b[2] for t, b in bars.items()}
            snapshot = snap_cache[persona]
            if snapshot is None:
                skipped += 1
                continue
            if _mirror_one(session, f, snapshot, close_cache[persona]):
                updated += 1
            else:
                skipped += 1

        log.info("mirror.done", date=str(today),
                 followers=len(follows), updated=updated, skipped=skipped)
        return {"followers": len(follows), "updated": updated, "skipped": skipped}

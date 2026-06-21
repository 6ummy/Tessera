"""live↔paper slippage comparison harness — Phase F scaffolding (observation).

Pure analysis, no orders. The paper engine fills at the next bar's OPEN with
no fees/impact; a real broker fills at whatever the live book gives. Before we
ever go live we want a frame to quantify that gap, and once live runs the
SAME-DAY comparison (Plan §8: "Compare live fills vs. paper fills on same day
→ quantify slippage") tells us whether paper P&L is a fair proxy.

This module just computes the diff from two fill sets the caller supplies; it
reads/writes nothing and places nothing. In the pilot there are no live fills,
so `slippage_report` returns an empty report — that's the expected state.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

Side = str  # "buy" | "sell"
Source = str  # "paper" | "live"


@dataclass(frozen=True, slots=True)
class Fill:
    ticker: str
    side: Side
    qty: float
    price: float
    source: Source  # "paper" or "live"


@dataclass(frozen=True, slots=True)
class TickerSlippage:
    ticker: str
    side: Side
    paper_price: float
    live_price: float
    # Signed slippage in basis points, expressed as COST: positive = the live
    # fill was worse than paper (paid more on a buy / received less on a sell).
    slippage_bps: float


@dataclass(frozen=True, slots=True)
class SlippageReport:
    pairs: list[TickerSlippage]
    avg_cost_bps: float | None  # mean signed cost across pairs, None if empty
    n_compared: int
    n_unmatched: int  # fills with no paper↔live counterpart to pair


def _cost_bps(side: Side, paper_price: float, live_price: float) -> float:
    """Slippage as a COST in bps. A buy filled above paper, or a sell filled
    below paper, is positive (worse). paper_price must be > 0."""
    raw = (live_price - paper_price) / paper_price
    signed = raw if side == "buy" else -raw  # selling lower is also a cost
    return signed * 10_000


def slippage_report(fills: list[Fill]) -> SlippageReport:
    """Pair paper and live fills by (ticker, side) and report per-pair +
    average slippage cost. Observation only. With no live fills (the pilot
    default) the report is empty."""
    paper: dict[tuple[str, Side], Fill] = {}
    live: dict[tuple[str, Side], Fill] = {}
    for f in fills:
        bucket = paper if f.source == "paper" else live
        bucket[(f.ticker, f.side)] = f

    pairs: list[TickerSlippage] = []
    for key, lf in live.items():
        pf = paper.get(key)
        if pf is None or pf.price <= 0:
            continue
        pairs.append(TickerSlippage(
            ticker=lf.ticker, side=lf.side,
            paper_price=pf.price, live_price=lf.price,
            slippage_bps=round(_cost_bps(lf.side, pf.price, lf.price), 2),
        ))
    matched_keys = {(p.ticker, p.side) for p in pairs}
    unmatched = sum(
        1 for k in set(paper) | set(live) if k not in matched_keys
    )
    avg = round(mean(p.slippage_bps for p in pairs), 2) if pairs else None
    return SlippageReport(
        pairs=pairs, avg_cost_bps=avg, n_compared=len(pairs), n_unmatched=unmatched,
    )

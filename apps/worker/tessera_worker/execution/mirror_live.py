"""Persona → Alpaca PAPER mirror — the pure diff between a persona's target
book and the account's current holdings. No DB, no network, no orders here;
the CLI (`jobs/alpaca_paper.py sync`) feeds it and decides whether to place
the orders. Equities/ETFs only (crypto is skipped upstream). Paper money only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Side = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class RebalanceLine:
    ticker: str
    target_weight: float   # 0..1 of equity
    price: float
    current_qty: float
    target_qty: float
    side: Side | None      # None = already in line

    @property
    def trade_qty(self) -> float:
        return abs(self.target_qty - self.current_qty)


def compute_rebalance(
    target_weights: dict[str, float],
    prices: dict[str, float],
    current_qty: dict[str, float],
    equity: float,
    *,
    min_notional: float = 1.0,
) -> list[RebalanceLine]:
    """Orders to make the account match the target book.

    target_qty = round(equity * weight / price). A holding not in the target
    (weight 0) is fully exited. Small adjustments below `min_notional` dollars
    are skipped to avoid churn. Whole-share rounding keeps the test legible.
    """
    lines: list[RebalanceLine] = []
    for ticker in sorted(set(target_weights) | set(current_qty)):
        w = float(target_weights.get(ticker, 0.0))
        price = float(prices.get(ticker, 0.0) or 0.0)
        cur = float(current_qty.get(ticker, 0.0))
        target = float(round(equity * w / price)) if (w > 0 and price > 0) else 0.0
        delta = target - cur
        side: Side | None = None
        if w <= 0 and cur != 0:
            side = "sell" if cur > 0 else "buy"  # fully exit a non-target holding
            target = 0.0
        elif delta != 0 and (price <= 0 or abs(delta) * price >= min_notional):
            side = "buy" if delta > 0 else "sell"
        lines.append(RebalanceLine(ticker, w, price, cur, target, side))
    return lines

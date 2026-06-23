"""Operator CLI to control the Alpaca PAPER account (simulated money).

Human-in-the-loop — NOT scheduled, NOT auto-invoked. Each command constructs
the AlpacaBroker, which refuses unless feature_alpaca_paper_execution=true AND
ALPACA_BASE_URL is the paper endpoint (so it can never reach real money).

  python -m tessera_worker.jobs.alpaca_paper account
  python -m tessera_worker.jobs.alpaca_paper positions
  python -m tessera_worker.jobs.alpaca_paper order --ticker AAPL --side buy --qty 1
  python -m tessera_worker.jobs.alpaca_paper cancel-all
  python -m tessera_worker.jobs.alpaca_paper sync --persona warren            # dry-run
  python -m tessera_worker.jobs.alpaca_paper sync --persona warren --execute  # place orders

`sync` mirrors a persona's current paper book onto the account: it prints the
diff (dry-run by default) and only places orders with --execute. The `order`
command places a single order immediately — running it IS the confirmation.
Exit 0 on success, 1 on failure / refusal.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import uuid

from tessera_worker.config import get_settings
from tessera_worker.execution.alpaca_broker import AlpacaBroker
from tessera_worker.execution.broker import LiveTradingNotCleared, OrderIntent
from tessera_worker.execution.mirror_live import RebalanceLine, compute_rebalance

# Alpaca paper supports equities/ETFs here; crypto symbols differ and are
# skipped for now (the equity weight stays in cash).
_TRADABLE = {"equity", "etf"}

with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


def _account(broker: AlpacaBroker) -> None:
    a = broker.get_account()
    print(f"account     : {a.get('account_number')}  ({a.get('status')})")
    print(f"cash        : ${float(a.get('cash', 0)):,.2f}")
    print(f"equity      : ${float(a.get('equity', 0)):,.2f}")
    print(f"buying_power: ${float(a.get('buying_power', 0)):,.2f}")


def _positions(broker: AlpacaBroker) -> None:
    positions = broker.get_positions()
    if not positions:
        print("no open positions")
        return
    for p in positions:
        print(f"{p.get('symbol'):<8} qty={p.get('qty'):<10} "
              f"mkt=${float(p.get('market_value', 0)):,.2f}  "
              f"upl=${float(p.get('unrealized_pl', 0)):,.2f}")


def _load_persona_target(persona: str) -> tuple[dict[str, float], dict[str, float], list[str]]:
    """(target_weights, ref_prices, skipped_non_equity) from the persona's
    latest real paper-book snapshot. Weights are value/total_value; ref price
    is the snapshot close. Crypto / unknown tickers are skipped."""
    from sqlalchemy import text

    from tessera_worker.db import session_scope
    from tessera_worker.universe import META_BY_TICKER

    with session_scope() as session:
        row = session.execute(text("""
            SELECT total_value, positions FROM persona_portfolios
            WHERE persona_id = :p AND NOT hypothetical
            ORDER BY ts DESC LIMIT 1
        """), {"p": persona}).first()
    if not row or not row.total_value:
        return {}, {}, []
    positions = row.positions if isinstance(row.positions, dict) else json.loads(row.positions)
    total = float(row.total_value)
    weights: dict[str, float] = {}
    prices: dict[str, float] = {}
    skipped: list[str] = []
    for ticker, v in positions.items():
        meta = META_BY_TICKER.get(ticker)
        if meta is None or meta.asset_class not in _TRADABLE:
            skipped.append(ticker)
            continue
        value = float(v.get("value") or 0.0)
        close = float(v.get("close") or 0.0)
        if value <= 0 or close <= 0 or total <= 0:
            continue
        weights[ticker] = value / total
        prices[ticker] = close
    return weights, prices, skipped


def _sync(broker: AlpacaBroker, persona: str, execute: bool) -> int:
    weights, snap_prices, skipped = _load_persona_target(persona)
    if not weights:
        print(f"no tradable book for persona {persona!r} (snapshot empty or all skipped)")
        return 1
    account = broker.get_account()
    equity = float(account.get("equity", 0.0))
    positions = broker.get_positions()
    current: dict[str, float] = {str(p["symbol"]): float(p["qty"]) for p in positions}
    live_prices = {str(p["symbol"]): float(p.get("current_price") or 0.0) for p in positions}
    prices = {**snap_prices, **{k: v for k, v in live_prices.items() if v > 0}}

    lines = compute_rebalance(weights, prices, current, equity)
    orders: list[RebalanceLine] = [ln for ln in lines if ln.side]

    print(f"persona={persona}  equity=${equity:,.0f}  "
          f"skipped(non-equity)={', '.join(skipped) or 'none'}")
    print(f"{'TICKER':<8}{'wt%':>6}{'price':>10}{'cur':>9}{'tgt':>9}  order")
    for ln in lines:
        order = f"{ln.side} {ln.trade_qty:g}" if ln.side else "-"
        print(f"{ln.ticker:<8}{ln.target_weight * 100:>5.1f}{ln.price:>10.2f}"
              f"{ln.current_qty:>9.3g}{ln.target_qty:>9.3g}  {order}")

    if not orders:
        print("\nalready in sync — no orders")
        return 0
    if not execute:
        print(f"\n[dry-run] {len(orders)} order(s). Re-run with --execute to place them.")
        return 0

    placed = 0
    for ln in orders:
        assert ln.side is not None
        res = broker.place_order(OrderIntent(
            ticker=ln.ticker, side=ln.side, qty=ln.trade_qty, confirm_token=str(uuid.uuid4()),
        ))
        print(f"  {ln.side} {ln.trade_qty:g} {ln.ticker}: "
              f"{'OK' if res.accepted else 'FAIL'}  {res.detail}")
        if res.accepted:
            placed += 1
    print(f"\nplaced {placed}/{len(orders)} order(s)")
    return 0 if placed == len(orders) else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="alpaca_paper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("account")
    sub.add_parser("positions")
    sub.add_parser("cancel-all")
    o = sub.add_parser("order")
    o.add_argument("--ticker", required=True)
    o.add_argument("--side", choices=["buy", "sell"], required=True)
    o.add_argument("--qty", type=float, required=True)
    sy = sub.add_parser("sync")
    sy.add_argument("--persona", required=True, choices=["warren", "cathie", "ray", "peter"])
    sy.add_argument("--execute", action="store_true", help="place the orders (default: dry-run)")
    args = parser.parse_args()

    try:
        broker = AlpacaBroker(get_settings())
    except LiveTradingNotCleared as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        print("  set FEATURE_ALPACA_PAPER_EXECUTION=true and ALPACA_BASE_URL to the "
              "paper endpoint to enable.", file=sys.stderr)
        return 1

    if args.cmd == "account":
        _account(broker)
    elif args.cmd == "positions":
        _positions(broker)
    elif args.cmd == "cancel-all":
        print(f"cancelled {broker.cancel_all()} open order(s)")
    elif args.cmd == "order":
        res = broker.place_order(OrderIntent(
            ticker=args.ticker.upper(), side=args.side, qty=args.qty,
            confirm_token=str(uuid.uuid4()),  # running the CLI is the confirmation
        ))
        print(f"order {'accepted' if res.accepted else 'REJECTED'}: "
              f"{res.detail}  id={res.broker_order_id}")
        return 0 if res.accepted else 1
    elif args.cmd == "sync":
        return _sync(broker, args.persona, args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Operator CLI to control the Alpaca PAPER account (simulated money).

Human-in-the-loop — NOT scheduled, NOT auto-invoked. Each command constructs
the AlpacaBroker, which refuses unless feature_alpaca_paper_execution=true AND
ALPACA_BASE_URL is the paper endpoint (so it can never reach real money).

  python -m tessera_worker.jobs.alpaca_paper account
  python -m tessera_worker.jobs.alpaca_paper positions
  python -m tessera_worker.jobs.alpaca_paper order --ticker AAPL --side buy --qty 1
  python -m tessera_worker.jobs.alpaca_paper cancel-all

The `order` command places a real (paper) order immediately — running it IS the
confirmation. Exit 0 on success, 1 on failure / refusal.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import uuid

from tessera_worker.config import get_settings
from tessera_worker.execution.alpaca_broker import AlpacaBroker
from tessera_worker.execution.broker import LiveTradingNotCleared, OrderIntent

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

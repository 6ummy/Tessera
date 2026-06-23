"""Alpaca PAPER broker adapter — places orders against the operator's Alpaca
PAPER trading account (SIMULATED money). NO REAL MONEY.

Two hard guards make it impossible to touch real money:
  1. ``feature_alpaca_paper_execution`` must be true (distinct from the
     real-money ``feature_live_trading``, which stays false).
  2. ``ALPACA_BASE_URL`` must be the Alpaca PAPER host
     (``paper-api.alpaca.markets``) — the constructor refuses anything else,
     so the real-money API (``api.alpaca.markets``) is physically unreachable
     from this adapter. Pointing at real money is a separate, deliberate change
     behind ``feature_live_trading``.

Uses the existing worker Alpaca key/secret (the operator's paper account).
Operator-only — there is one account and no per-user routing. Not auto-invoked;
driven by the operator CLI (`jobs/alpaca_paper.py`), human-in-the-loop.
"""

from __future__ import annotations

from typing import Any, cast

import httpx

from tessera_worker.config import Settings
from tessera_worker.execution.broker import (
    LiveTradingNotCleared,
    OrderIntent,
    OrderResult,
)
from tessera_worker.logging import get_logger

log = get_logger(__name__)

_PAPER_HOST = "paper-api.alpaca.markets"
_TIMEOUT = 15.0


class AlpacaBroker:
    """Order routing to Alpaca PAPER. is_live=True (it does place real orders),
    but only ever against the simulated paper account."""

    is_live = True

    def __init__(self, settings: Settings) -> None:
        if not settings.feature_alpaca_paper_execution:
            raise LiveTradingNotCleared("feature_alpaca_paper_execution is off")
        base = (settings.alpaca_base_url or "").rstrip("/")
        if _PAPER_HOST not in base:
            raise LiveTradingNotCleared(
                f"refusing: ALPACA_BASE_URL={base!r} is not the Alpaca PAPER endpoint "
                f"({_PAPER_HOST}); this adapter is paper-only",
            )
        if not settings.alpaca_api_key or not settings.alpaca_api_secret:
            raise LiveTradingNotCleared("alpaca api key/secret not set")
        self._base = base
        self._headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        }

    def _get(self, path: str) -> Any:
        r = httpx.get(f"{self._base}{path}", headers=self._headers, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def get_account(self) -> dict[str, Any]:
        return cast("dict[str, Any]", self._get("/v2/account"))

    def get_positions(self) -> list[dict[str, Any]]:
        return cast("list[dict[str, Any]]", self._get("/v2/positions"))

    def place_order(self, intent: OrderIntent) -> OrderResult:
        # Every order is explicitly confirmed (the CLI mints the token when the
        # operator runs the command) — no silent execution.
        if not intent.confirm_token:
            raise LiveTradingNotCleared("order has no per-order confirm token")
        payload = {
            "symbol": intent.ticker,
            "qty": str(intent.qty),
            "side": intent.side,
            "type": "market",
            "time_in_force": "day",
        }
        r = httpx.post(
            f"{self._base}/v2/orders", headers=self._headers, json=payload, timeout=_TIMEOUT,
        )
        if r.status_code in (200, 201):
            data = r.json()
            log.info("alpaca_paper.order_placed", ticker=intent.ticker, side=intent.side,
                     qty=intent.qty, order_id=data.get("id"), status=data.get("status"))
            return OrderResult(
                accepted=True, broker_order_id=data.get("id"),
                detail=f"alpaca-paper:{data.get('status')}",
            )
        log.warning("alpaca_paper.order_rejected", ticker=intent.ticker,
                    status=r.status_code, detail=r.text[:200])
        return OrderResult(accepted=False, broker_order_id=None,
                           detail=f"alpaca {r.status_code}: {r.text[:200]}")

    def cancel_all(self) -> int:
        """Kill switch — cancel all open orders. (Closing positions is a
        separate explicit step.)"""
        r = httpx.delete(f"{self._base}/v2/orders", headers=self._headers, timeout=_TIMEOUT)
        if r.status_code in (200, 207):
            cancelled = len(cast("list[Any]", r.json()))
            log.info("alpaca_paper.cancel_all", cancelled=cancelled)
            return cancelled
        log.warning("alpaca_paper.cancel_all_failed", status=r.status_code)
        return 0

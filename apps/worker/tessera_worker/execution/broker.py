"""Broker execution abstraction — Phase F scaffolding (OFF-gated).

⚠️  LIVE TRADING IS NOT ENABLED AND CANNOT BE FROM THIS MODULE.  ⚠️

The whole product is paper-trading only. This module exists so the Phase F
execution seam + its safety gates are designed and reviewable BEFORE any
real-money code lands — not to enable trading. `get_broker()` returns the
`PaperBroker` unconditionally in the pilot because the two gate flags default
to False.

Defense in depth — a live order requires ALL of:
  1. ``settings.feature_live_trading``          — the kill-flag. Never flip it
     until legal clearance (CLAUDE.md #1 invariant).
  2. ``settings.feature_live_trading_cleared``  — a SEPARATE flag recording the
     Phase E compliance sign-off, so a stray ``feature_live_trading=true``
     can't reach real money on its own.
  3. a per-order ``confirm_token``              — every order is explicitly
     user-confirmed; there is no silent / automatic live execution.

Even when all three are present, ``LiveBroker`` is still a STUB that raises
``NotImplementedError`` — no Alpaca (or any) live-order API is imported or
called here. The real adapter is a separate, deliberately-reviewed PR that
lands only after Phase E. The existing nightly paper engine (`risk/paper_
engine.py`) remains the sole execution path until then; this layer is not yet
wired into it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from tessera_worker.config import Settings
from tessera_worker.logging import get_logger

log = get_logger(__name__)

Side = Literal["buy", "sell"]


class LiveTradingNotCleared(RuntimeError):
    """Raised when a live order is attempted before every gate is satisfied."""


@dataclass(frozen=True, slots=True)
class OrderIntent:
    ticker: str
    side: Side
    qty: float
    # Present only when the user explicitly confirmed THIS specific order.
    # The live path refuses any intent without it.
    confirm_token: str | None = None


@dataclass(frozen=True, slots=True)
class OrderResult:
    accepted: bool
    broker_order_id: str | None
    detail: str


@runtime_checkable
class BrokerAdapter(Protocol):
    """What the future order router will depend on — paper or (eventually) live."""

    @property
    def is_live(self) -> bool: ...

    def place_order(self, intent: OrderIntent) -> OrderResult: ...

    def cancel_all(self) -> int:  # the kill switch — close/cancel everything
        ...


class PaperBroker:
    """The only broker in use. No real money — an order is just recorded; the
    deterministic paper engine fills it at the next bar (existing behaviour).
    Kept as a thin adapter so the order router can be broker-agnostic later."""

    is_live = False

    def place_order(self, intent: OrderIntent) -> OrderResult:
        log.info("paper_broker.order", ticker=intent.ticker, side=intent.side, qty=intent.qty)
        return OrderResult(accepted=True, broker_order_id=None, detail="paper")

    def cancel_all(self) -> int:
        return 0


class LiveBroker:
    """STUB. Refuses to trade until every Phase-F gate passes, and even then
    raises ``NotImplementedError`` — no live-order API is wired. Exists only so
    the gate logic is testable + reviewable."""

    is_live = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _require_clearance(self, intent: OrderIntent | None) -> None:
        s = self._settings
        if not s.feature_live_trading:
            raise LiveTradingNotCleared("FEATURE_LIVE_TRADING is off")
        if not s.feature_live_trading_cleared:
            raise LiveTradingNotCleared("compliance clearance (Phase E) not recorded")
        if intent is not None and not intent.confirm_token:
            raise LiveTradingNotCleared("order has no per-order confirmation token")

    def place_order(self, intent: OrderIntent) -> OrderResult:
        self._require_clearance(intent)
        # Only reachable with both flags set + a confirm token — still a stub.
        raise NotImplementedError("live order adapter not implemented (Phase F, post-Phase-E)")

    def cancel_all(self) -> int:
        self._require_clearance(None)
        raise NotImplementedError("live kill switch not implemented (Phase F, post-Phase-E)")


def get_broker(settings: Settings) -> BrokerAdapter:
    """The active broker. Returns ``PaperBroker`` unless BOTH live gates are
    set; even then it returns the refusing/stub ``LiveBroker`` — never a path
    that silently moves real money. In the pilot the flags default False, so
    this is always the paper broker."""
    if settings.feature_live_trading and settings.feature_live_trading_cleared:
        log.warning("broker.live_selected", note="LiveBroker is still a stub — no real orders")
        return LiveBroker(settings)
    return PaperBroker()

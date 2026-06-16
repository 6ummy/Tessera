"""Risk gateway — the Decision Plane's final stop before a book persists.

Deterministic Python only, no LLM calls. The v2 construction pass already
*aims* for these constraints (the prompt embeds them and `normalize_book`
deterministically enforces sum=1.0 + the single-name cap), so this gateway
is the thin validator the 2026-06-11 improvement plan scoped — NOT the
original reject-and-retry engine. What it adds on top of the normalizer:

  - **universe membership** — the construction LLM sizes from research
    notes, but nothing upstream guarantees it didn't invent a ticker.
    This is the last line of the "no hallucinated tickers" hard rule
    (architecture.md §9) for the persistence path.
  - **sector cap** — `normalize_book` knows nothing about sectors; the
    cap was prompt-only until this gateway. Sector comes from
    `universe.META_BY_TICKER`.
  - **re-checks** sum=1.0 and the single-name cap as belt-and-suspenders
    (a refactor that bypasses the normalizer should fail here, loudly).

Soft checks (logged, never fail the gate):
  - cash outside [cash_min, cash_max] — the normalizer legitimately
    exceeds cash_max when the persona's shortlist × caps can't reach a
    1.0 book ("impossible envelope"); construction already logs it.
  - active position below min_active_conviction — voice/spec drift,
    canary territory, not a risk event.

Ray is NOT gated here: his RegimeReport never passes through
`construct_portfolio`, and its schema already enforces the per-slice cap
(0.40) + probabilities summing to 1.0. A regime-aware gate joins when the
paper engine starts executing his allocations.

`current_portfolio` is accepted but unused until the paper engine exists —
the parametric-VaR and drawdown-floor checks from Plan.md §5 need live
positions to mean anything.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from tessera_shared.schemas import AnalystReport, RegimeReport, RiskCheckResult

from tessera_worker.agents.persona_constraints import constraints_for
from tessera_worker.logging import get_logger
from tessera_worker.risk.var import MarketContext, parametric_var99
from tessera_worker.universe import META_BY_TICKER

log = get_logger(__name__)

# normalize_book rounds weights to 0.01 — allow 1pp of accumulated
# rounding before calling a sum violation real.
SUM_TOLERANCE = 0.011
# Caps are enforced exactly upstream; only float dust gets a pass.
CAP_TOLERANCE = 1e-6


def _market_risk_reasons(
    persona: str,
    weights: dict[str, float],
    market: MarketContext | None,
) -> list[str]:
    """VaR + drawdown-floor checks, shared by both book shapes.

    No market context (unit tests, dry paths) → both checks skip. VaR
    unresolvable from data (young listings, <60 aligned obs) → soft log,
    never a rejection — "can't measure" must not block the desk, the
    threshold exists to catch books we CAN measure drifting far out."""
    if market is None:
        return []
    constraints = constraints_for(persona)  # type: ignore[arg-type]
    reasons: list[str] = []

    var99 = parametric_var99(weights, market.returns)
    if var99 is None:
        if weights:
            log.info("risk_gateway.var_unavailable", persona=persona,
                     n_positions=len(weights),
                     hint="<60 aligned return obs for some holding")
    elif var99 > constraints.max_var99_1d + CAP_TOLERANCE:
        reasons.append(
            f"book 1-day VaR99 {var99:.2%} > persona cap "
            f"{constraints.max_var99_1d:.2%} — reduce gross exposure or "
            f"the highest-volatility names"
        )
    else:
        log.info("risk_gateway.var_ok", persona=persona,
                 var99=round(var99, 4), cap=constraints.max_var99_1d)

    dd = market.current_drawdown
    if dd is not None and dd > constraints.max_drawdown + CAP_TOLERANCE:
        reasons.append(
            f"live track drawdown {dd:.2%} breaches the persona floor "
            f"{constraints.max_drawdown:.2%} — auto-execution paused, "
            f"operator review required"
        )
    return reasons


def gate(
    report: AnalystReport,
    *,
    market: MarketContext | None = None,
    current_portfolio: Any | None = None,
) -> RiskCheckResult:
    """Validate a stock-picker AnalystReport against the persona's hard
    constraints. Returns RiskCheckResult — ok=False carries every reason
    found (not just the first) so retry feedback can fix the whole book
    in one pass. `market` enables the VaR + drawdown checks; without it
    only the structural checks run (universe/sum/caps)."""
    persona = report.persona_id
    constraints = constraints_for(persona)
    reasons: list[str] = []

    # 1 — universe membership (anti-hallucination, final stop).
    unknown = [p.ticker for p in report.proposals if p.ticker not in META_BY_TICKER]
    if unknown:
        reasons.append(f"tickers not in universe: {sorted(unknown)}")

    # 2 — conservation of NAV.
    sum_positions = sum(p.target_weight for p in report.proposals)
    total = sum_positions + report.cash_target
    if abs(total - 1.0) > SUM_TOLERANCE:
        reasons.append(
            f"book sum {total:.4f} != 1.0 "
            f"(positions {sum_positions:.4f} + cash {report.cash_target:.4f})"
        )

    # 3 — single-name cap.
    for p in report.proposals:
        if p.target_weight > constraints.max_single_name + CAP_TOLERANCE:
            reasons.append(
                f"{p.ticker} weight {p.target_weight:.4f} > single-name cap "
                f"{constraints.max_single_name:.2f}"
            )

    # 4 — sector cap. Unknown tickers are already flagged in (1); skip
    # them here so one bad ticker doesn't double-report. max_sector >= 1.0
    # means the persona has no operational sector cap (Cathie — sector
    # concentration is her mandate, not a risk to fence; see
    # persona_constraints). We still tally sector_weights for the audit log.
    sector_weights: dict[str, float] = defaultdict(float)
    for p in report.proposals:
        meta = META_BY_TICKER.get(p.ticker)
        if meta is not None:
            sector_weights[meta.sector] += p.target_weight
    if constraints.max_sector < 1.0:
        for sector, weight in sorted(sector_weights.items()):
            if weight > constraints.max_sector + CAP_TOLERANCE:
                reasons.append(
                    f"sector '{sector}' weight {weight:.4f} > sector cap "
                    f"{constraints.max_sector:.2f}"
                )

    # ── Soft checks — logged for audit, never fail the gate ──────────
    if not (constraints.cash_min - CAP_TOLERANCE
            <= report.cash_target
            <= constraints.cash_max + CAP_TOLERANCE):
        log.info("risk_gateway.cash_outside_range",
                 persona=persona,
                 cash=round(report.cash_target, 4),
                 cash_min=constraints.cash_min,
                 cash_max=constraints.cash_max,
                 hint="normalizer impossible-envelope fallback is the usual cause")
    weak = [
        p.ticker for p in report.proposals
        if p.target_weight > CAP_TOLERANCE
        and p.conviction < constraints.min_active_conviction
    ]
    if weak:
        log.info("risk_gateway.active_below_conviction_floor",
                 persona=persona, tickers=weak,
                 floor=constraints.min_active_conviction)

    # 5 — market risk (VaR + drawdown floor) when context is provided.
    weights = {
        p.ticker: p.target_weight
        for p in report.proposals if p.target_weight > 0
    }
    reasons += _market_risk_reasons(persona, weights, market)

    if reasons:
        log.warning("risk_gateway.rejected",
                    persona=persona, n_reasons=len(reasons), reasons=reasons)
        return RiskCheckResult.failed(*reasons)

    log.info("risk_gateway.passed",
             persona=persona,
             n_positions=len(report.proposals),
             sum_positions=round(sum_positions, 4),
             cash=round(report.cash_target, 4),
             sectors={s: round(w, 3) for s, w in sector_weights.items()})
    return RiskCheckResult.passed()


def gate_regime(
    report: RegimeReport,
    *,
    market: MarketContext | None = None,
) -> RiskCheckResult:
    """Ray's gate. His RegimeReport schema already enforces the per-slice
    cap (≤0.40) and regime probabilities summing to 1.0, so this adds the
    same final stops the stock-picker gate provides: universe membership
    of every instrument, conservation of NAV, a slice-cap re-check, and
    the VaR / drawdown-floor market checks."""
    constraints = constraints_for("ray")
    reasons: list[str] = []

    unknown = [
        a.instrument for a in report.allocations
        if a.instrument not in META_BY_TICKER
    ]
    if unknown:
        reasons.append(f"instruments not in universe: {sorted(unknown)}")

    sum_alloc = sum(a.target_weight for a in report.allocations)
    total = sum_alloc + report.cash_target
    if abs(total - 1.0) > SUM_TOLERANCE:
        reasons.append(
            f"allocations sum {total:.4f} != 1.0 "
            f"(slices {sum_alloc:.4f} + cash {report.cash_target:.4f})"
        )

    for a in report.allocations:
        if a.target_weight > constraints.max_single_name + CAP_TOLERANCE:
            reasons.append(
                f"{a.instrument} slice {a.target_weight:.4f} > cap "
                f"{constraints.max_single_name:.2f}"
            )

    weights = {
        a.instrument: a.target_weight
        for a in report.allocations if a.target_weight > 0
    }
    reasons += _market_risk_reasons("ray", weights, market)

    if reasons:
        log.warning("risk_gateway.regime_rejected",
                    n_reasons=len(reasons), reasons=reasons)
        return RiskCheckResult.failed(*reasons)
    log.info("risk_gateway.regime_passed",
             n_slices=len(report.allocations),
             cash=round(report.cash_target, 4))
    return RiskCheckResult.passed()

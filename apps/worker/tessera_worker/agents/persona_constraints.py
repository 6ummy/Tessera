"""Per-persona portfolio construction constraints.

Reads as the rulebook the construction-pass LLM is given alongside the
research notes. Values are the operational reading of each persona's
spec in personalities.md — concentration philosophy, risk appetite,
cash discipline, scoring threshold for an active vs watchlist slot.

The construction prompt embeds these verbatim; the construction LLM
output is then schema-validated against the same numbers via
`schemas.AnalystReport.weights_sum_to_one_or_less` plus a downstream
Phase-C risk gateway check.

Why these are not in personalities.md itself: the prose specs read
naturally for prompt context ("concentrated bets only when valuations
compensate"), but the construction agent needs precise numerics. We
keep both: prose in personalities.md drives voice; numerics here drive
sizing math. When they drift, update both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PersonaId = Literal["warren", "cathie", "peter", "ray"]


@dataclass(frozen=True, slots=True)
class PortfolioConstraints:
    """The envelope the construction LLM must satisfy.

    All fractions are of NAV (0.0–1.0). Inclusive bounds.
    """

    # Per-position caps (active book only — watchlist entries don't claim NAV)
    max_single_name: float
    """Hard ceiling on any one position. Schema enforces ≤0.40."""

    max_sector: float
    """Hard ceiling on any one sector. Schema enforces ≤0.60."""

    # Cash discipline
    cash_min: float
    """Lower bound on cash_target. Warren's "if I see nothing, I hold cash"
    means his min is 0; Peter's discipline keeps him with a small float."""

    cash_max: float
    """Upper bound on cash_target. Cathie's mandate forbids holding much
    cash — equity exposure is the point. Warren's mandate allows up to
    a full cash book (1.0) if no bargain is found."""

    # Scoring thresholds — applied by the construction LLM, not just the
    # research call. A name landing above min_active_conviction MAY be
    # sized; below, it's watchlist only. min_strong_conviction promotes
    # a name to the top of the sizing queue (≥ persona's typical mid-cap).
    min_active_conviction: float
    """Below this conviction the construction call must leave the slot
    watchlist (target_weight=0). Warren's high bar reflects his quote:
    "we don't get paid for activity, only for being right.""
    """

    min_strong_conviction: float
    """At or above this, the construction call treats the name as a
    top-of-book candidate. Used by the prompt language ("size into the
    high-conviction names first"); not a hard cap."""

    # Position count guidance (soft — informs the prompt, not a hard
    # cap, since some personas legitimately concentrate or diversify
    # based on opportunity set).
    target_position_count_min: int
    """Floor on the active book size. Stops Warren shipping a one-name
    portfolio just because his shortlist had a bad week."""

    target_position_count_max: int
    """Ceiling on active book size. Stops Cathie spraying across all 14
    candidates at single-digit-percent weights."""

    # Market-risk limits — enforced by risk/gateway.py with inputs from
    # risk/var.py (added 2026-06-12 once paper positions existed).
    max_var99_1d: float = 0.10
    """Hard ceiling on the book's one-day parametric VaR at 99%, as a
    fraction of NAV. Delta-normal estimate understates fat tails, so
    these carry headroom over each persona's measured book VaR — the
    gate exists to catch a book whose gross risk DRIFTED far past the
    mandate, not to fine-tune sizing."""

    max_drawdown: float = 0.50
    """Drawdown floor: when the persona's LIVE paper track is already
    down more than this from peak, the gateway refuses to auto-execute a
    new book — an operator looks first. Hypothetical backfill rows never
    count toward this."""


# ─────────────────────────────────────────────────────────────────────────
# Per-persona values — operational reading of personalities.md
# ─────────────────────────────────────────────────────────────────────────
PERSONA_CONSTRAINTS: dict[PersonaId, PortfolioConstraints] = {
    # ── Warren — Conservative value investor ───────────────────────────
    # "Concentrated portfolio of companies with durable moats." High
    # single-name cap (he'll go 20%+ on top conviction). Cash unbounded
    # by mandate — if nothing is cheap, he holds.
    "warren": PortfolioConstraints(
        max_single_name=0.18,
        max_sector=0.50,
        cash_min=0.00,
        cash_max=1.00,
        min_active_conviction=0.65,
        min_strong_conviction=0.80,
        target_position_count_min=3,
        target_position_count_max=10,
        max_var99_1d=0.035,   # measured book VaR99 1.6% on 2026-06-12
        max_drawdown=0.20,
    ),
    # ── Cathie — Disruptive growth ─────────────────────────────────────
    # Concentrated by S-curve sector, single names sized to asymmetry.
    # Mandate forbids large cash drag; equity exposure IS the position.
    # Crypto sleeve is its own envelope; this is the equity-side cap.
    "cathie": PortfolioConstraints(
        max_single_name=0.16,
        max_sector=0.50,
        cash_min=0.00,
        cash_max=0.10,
        min_active_conviction=0.50,
        min_strong_conviction=0.75,
        target_position_count_min=10,
        target_position_count_max=20,
        max_var99_1d=0.085,   # measured 5.1% (crypto sleeve) — high-risk mandate
        max_drawdown=0.35,
    ),
    # ── Peter — GARP, diversified by growth-driver ─────────────────────
    # Many smaller positions across sectors. Strict on single-name risk
    # because growth-at-reasonable-price means thesis can break on a
    # single earnings print. Mandate carries 5-15% cash for opportunistic
    # adds, sometimes higher when the screen comes up short.
    #
    # 2026-06-10: bumped max_single_name 0.08 → 0.10 and cash_max
    # 0.15 → 0.25 because the current 10-ticker shortlist couldn't reach
    # a coherent sum=1.0 book inside the old envelope (10 × 0.08 = 0.80
    # max, + 0.15 cash = 0.95 ceiling). Either widen the shortlist past
    # 15 names OR widen the caps. The latter ships first; the former is
    # a research-track task.
    "peter": PortfolioConstraints(
        max_single_name=0.10,
        max_sector=0.35,
        cash_min=0.05,
        cash_max=0.25,
        min_active_conviction=0.50,
        min_strong_conviction=0.70,
        target_position_count_min=8,
        target_position_count_max=30,
        max_var99_1d=0.045,   # measured 2.1%
        max_drawdown=0.25,
    ),
    # ── Ray — Regime allocator (asset-class slices) ────────────────────
    # NOT a stock picker. The construction agent treats Ray differently:
    # input is regime probability snapshot + asset-class research, output
    # is a RegimeAllocation list. These caps apply to single asset-class
    # slices (US equities, long Treasuries, gold, etc.), not single
    # equity tickers — so max_single_name reads as max_slice.
    "ray": PortfolioConstraints(
        max_single_name=0.40,
        max_sector=0.60,
        cash_min=0.00,
        cash_max=0.30,
        min_active_conviction=0.0,  # Regime sizing doesn't use conviction
        min_strong_conviction=0.0,
        target_position_count_min=5,
        target_position_count_max=8,
        max_var99_1d=0.025,   # measured 1.0% — allocator must stay low-risk
        max_drawdown=0.15,
    ),
}


def constraints_for(persona: PersonaId) -> PortfolioConstraints:
    """Get the construction constraints for a persona. Raises KeyError on
    unknown persona — defaulting silently would mask a routing bug."""
    return PERSONA_CONSTRAINTS[persona]


def constraints_prompt_block(persona: PersonaId) -> str:
    """Format the constraints as a prose block the construction LLM can
    read inline. Used by `portfolio_construction.build_prompt()`."""
    c = constraints_for(persona)
    lines = [
        f"- Single-name cap: {c.max_single_name * 100:.0f}% of NAV.",
        f"- Sector cap: {c.max_sector * 100:.0f}% of NAV.",
        f"- Cash range: {c.cash_min * 100:.0f}%–{c.cash_max * 100:.0f}%.",
        f"- Active positions: {c.target_position_count_min}–{c.target_position_count_max} names.",
        f"- A candidate qualifies for sizing at conviction ≥ {c.min_active_conviction:.2f}. "
        f"Below that, list it on the watchlist (target_weight=0).",
        f"- Treat conviction ≥ {c.min_strong_conviction:.2f} as a top-of-book candidate "
        f"and size into it before filling smaller slots.",
        "- Active position weights plus cash MUST sum to exactly 1.0.",
    ]
    return "\n".join(lines)

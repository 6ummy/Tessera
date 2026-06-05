"""Pydantic schemas — the contract between LLM output, validators, and execution.

These types are authoritative. Anywhere an LLM produces structured output, it
MUST conform to one of these models or be rejected. The Risk Gateway operates
on these types and nothing else.

Field-level constraints encode persona hard rules (e.g., Warren's 18% cap).
Persona-specific tightening is layered on top via `validate_for_persona()`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ── Type aliases ──────────────────────────────────────────────────────────
PersonaId = Literal["warren", "cathie", "ray", "peter"]
RiskLabel = Literal["Conservative", "Balanced", "Aggressive"]
Side = Literal["buy", "sell", "hold", "trim", "add"]


# ── Static persona metadata (mirrors lib/mock/personas.ts on the web side) ──
class Persona(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: PersonaId
    name: str
    archetype: str
    age: int = Field(ge=18, le=120)
    photo: str  # relative path under apps/web/public
    risk_label: RiskLabel
    horizon: str
    max_single_name: float = Field(gt=0, le=0.4, description="Cap on any one position, fraction")
    max_sector: float = Field(gt=0, le=0.6, description="Cap on any one sector, fraction")
    min_conviction: float = Field(ge=0, le=1, description="Below this, persona will not propose")


# ── LLM output: a single proposed position ───────────────────────────────
class Proposal(BaseModel):
    """One position a persona proposes. Output by the LLM, validated downstream.

    Note: `target_weight` is currently LLM-decided. The risk register flags
    "mode collapse" as a risk; if observed during Phase C, refactor to LLM
    outputting `conviction` only and Python deriving `target_weight`.
    """

    ticker: str = Field(min_length=1, max_length=8)
    side: Side
    target_weight: float = Field(ge=0, le=0.20, description="Fraction of NAV. Persona cap enforced separately.")
    horizon_days: int = Field(ge=1, le=3650)
    conviction: float = Field(ge=0, le=1)
    thesis_md: str = Field(min_length=20, max_length=2500)
    # max_length 8: Cathie's voice naturally enumerates 6-7 distinct risks
    # (scenario-structured personality). Cap at 8 stays manageable for the
    # UI cards while not chopping a meaningful enumerated thought in half.
    # Bumped 5→8 after 2026-06-04 backtest: 3 of 4 schema failures were
    # Cathie outputting exactly 6 well-formed risks.
    what_would_make_me_wrong: list[str] = Field(default_factory=list, max_length=8)
    cited_news_ids: list[UUID] = Field(default_factory=list, max_length=10)
    add_trigger: str | None = Field(default=None, description="Peter requires this; others optional")
    trim_trigger: str | None = Field(default=None, description="Peter requires this; others optional")


# ── LLM output: a full report (one persona, one day) ─────────────────────
class AnalystReport(BaseModel):
    persona_id: PersonaId
    as_of: date
    proposals: list[Proposal] = Field(default_factory=list, max_length=30)
    cash_target: float = Field(ge=0, le=1)
    notes_to_manager: str = Field(default="", max_length=500)
    inputs_hash: str = Field(description="SHA256 of the feature snapshot the LLM read")
    model: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def weights_sum_to_one_or_less(self) -> AnalystReport:
        total = self.cash_target + sum(p.target_weight for p in self.proposals)
        if total > 1.001:  # tiny float tolerance
            raise ValueError(f"weights + cash = {total:.4f} > 1.0")
        return self


# ── Ray's specific output (regime allocator, not stock picker) ────────────
class RegimeProbabilities(BaseModel):
    goldilocks_prob: float = Field(ge=0, le=1)
    reflation_prob: float = Field(ge=0, le=1)
    stagflation_prob: float = Field(ge=0, le=1)
    deflation_prob: float = Field(ge=0, le=1)
    delta_from_last_week_md: str = Field(max_length=400)

    @model_validator(mode="after")
    def probabilities_sum_to_one(self) -> RegimeProbabilities:
        total = self.goldilocks_prob + self.reflation_prob + self.stagflation_prob + self.deflation_prob
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"regime probabilities sum to {total:.4f}, must be 1.0 ± 0.01")
        return self


# ── Ray's full daily output: regime + asset-class allocations ─────────────
class RegimeAllocation(BaseModel):
    """One asset-class slice of Ray's portfolio. Uses an ETF instrument
    instead of a single stock ticker because Ray is an allocator, not a
    stock picker. Higher per-slice cap (0.40) than Proposal (0.20)."""

    asset_class: str = Field(min_length=1, max_length=60,
                             description="e.g. 'US equities', 'Long Treasuries', 'Gold'")
    instrument: str = Field(min_length=1, max_length=8,
                            description="ETF ticker, e.g. VTI, IEF, TLT, GLD, DBC, VXUS, TIP")
    target_weight: float = Field(ge=0, le=0.40,
                                 description="Fraction of NAV; allocator cap higher than stock-picker")
    thesis_md: str = Field(min_length=20, max_length=1200)


class RegimeReport(BaseModel):
    """Ray's daily output. Persisted to the same `analyst_reports` table as
    AnalystReport; the discriminator is `persona_id='ray'` and the parsed
    JSONB has this shape instead of AnalystReport's. Frontend / risk
    gateway switch on persona_id when deciding which schema to read."""

    persona_id: Literal["ray"]
    as_of: date
    regime: RegimeProbabilities
    allocations: list[RegimeAllocation] = Field(default_factory=list, max_length=10)
    cash_target: float = Field(ge=0, le=1)
    notes_to_manager: str = Field(default="", max_length=500)
    inputs_hash: str = Field(description="SHA256 of the macro snapshot Ray read")
    model: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def weights_sum_to_one_or_less(self) -> RegimeReport:
        total = self.cash_target + sum(a.target_weight for a in self.allocations)
        if total > 1.001:
            raise ValueError(f"allocations + cash = {total:.4f} > 1.0")
        return self


# ── State (not LLM output): portfolio and positions ───────────────────────
class Position(BaseModel):
    ticker: str
    qty: float
    avg_cost: float = Field(ge=0)


class Portfolio(BaseModel):
    persona_id: PersonaId
    as_of: datetime
    cash: float = Field(ge=0)
    positions: list[Position] = Field(default_factory=list)
    total_value: float = Field(ge=0)


class PersonaPerformance(BaseModel):
    persona_id: PersonaId
    date: date
    pnl_day: float
    pnl_cum: float
    return_day: float
    return_cum: float
    sharpe_30d: float | None = None
    mdd_30d: float | None = None
    hit_rate: float | None = Field(default=None, ge=0, le=1)
    trades_count: int = Field(ge=0, default=0)


# ── Risk gateway result ──────────────────────────────────────────────────
class RiskCheckResult(BaseModel):
    ok: bool
    reasons: list[str] = Field(default_factory=list, description="Empty when ok=True")

    @classmethod
    def passed(cls) -> RiskCheckResult:
        return cls(ok=True)

    @classmethod
    def failed(cls, *reasons: str) -> RiskCheckResult:
        return cls(ok=False, reasons=list(reasons))


# ── Chat ──────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: Literal["user", "analyst"]
    content: str
    ts: datetime

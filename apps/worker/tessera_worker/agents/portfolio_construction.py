"""Portfolio construction agent — second pass of the 2-pass persona flow.

Wires to anthropic_runner. The foundation PR (#79) shipped the prompt
template + constraint registry; this lands the actual LLM call,
parsing, and persistence.

# Two-pass overview

  Pass 1 — RESEARCH  (per ticker, runs sequentially across cells)
    `run_research(persona, ticker)` → TickerResearch
    Lighter than the old run_thesis — no `target_weight`, no
    `cash_target`, no `side`. Pure judgment on this one name.

  Pass 2 — CONSTRUCTION  (one call per persona per batch)
    `construct_portfolio(persona, research_notes)` → AnalystReport
    persisted as ONE row in analyst_reports. Pydantic enforces
    `proposals + cash_target = 1.0`.

# Cost

Construction call is one shot per persona per batch (~2-3K tokens in
of research summaries, ~1K out of structured portfolio JSON). Across 4
personas weekly: ~$0.32/week. Research calls drop ~$0.02 each by
losing the sizing section. Net cost: roughly flat with single-pass.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import structlog
from anthropic import Anthropic

from tessera_worker.agents.models import AnalystReport, PersonaId
from tessera_worker.agents.persona_constraints import (
    constraints_for,
    constraints_prompt_block,
)
from tessera_worker.agents.persona_loader import load_persona_specs
from tessera_worker.config import get_settings

log = structlog.get_logger(__name__)


def build_construction_prompt(
    persona: PersonaId,
    research_payload: str,
    as_of: date,
) -> str:
    """Assemble the user-content block for the construction call.

    `research_payload` is the rendered Pass-1 research output for ALL
    candidates this batch — a numbered list of `TickerResearch` blocks.
    """
    constraints_block = constraints_prompt_block(persona)

    return f"""You are sitting down at the end of the research week.
Below are the notes your team prepared on every candidate they screened.
Each candidate has a conviction score and a written thesis.

Today is {as_of.isoformat()}. Build this week's book.

# Research notes

{research_payload}

# Your hard rules

{constraints_block}

# What to output

Return ONLY a JSON object with this shape:

{{
  "cash_target": <fraction 0..1>,
  "proposals": [
    {{
      "ticker": "<symbol from the research notes>",
      "side": "buy" | "hold" | "trim" | "add",
      "target_weight": <fraction 0..0.20>,
      "horizon_days": <int>,
      "conviction": <0..1, from the research note>,
      "thesis_md": "<1-2 sentences of SIZING reasoning only — why THIS weight vs the other candidates. Do NOT repeat the full research thesis; that's already on file. Keep total length under 500 characters.>",
      "what_would_make_me_wrong": ["<short bullet>", ...]
    }}
  ],
  "notes_to_manager": "<3-5 sentences on what the book reflects, any constraint conflicts surfaced, theme calls. Under 1500 characters.>"
}}

Active proposals + cash_target MUST sum to exactly 1.0.

Do the math BEFORE writing the JSON. Sum all your target_weights. Add
cash_target. The total has to equal 1.0 within 1pp tolerance. If you
write 8 positions at the 16% cap, that's 1.28 — too much, you must
size most below the cap. If you write 4 positions averaging 10%,
that's 0.40 with cash maybe 0.10 — only 0.50, too little. The book
must be FULLY ALLOCATED inside the persona's cash range.

If you only see a handful of high-conviction names and worry the book
is too concentrated, size the next conviction tier too — sized
exposure beats an unsourced cash holding when the persona mandate
forbids large cash drag. Your cash_target MUST stay inside the cash
range above. If even after sizing every reasonable candidate the book
still wouldn't sum to 1.0, you've found a contradiction with the
constraints — surface it briefly in `notes_to_manager` and size the
book to the closest legal allocation, but DO NOT silently leave the
total below 1.0.

Names that don't qualify for sizing get OMITTED — don't include
target_weight=0 rows. Their research notes are already on file.
Return JSON only, no markdown fences, no commentary."""


def format_research_payload(research_notes: list[dict[str, Any]]) -> str:
    """Render TickerResearch list as a numbered prompt block."""
    if not research_notes:
        return "(no research notes — empty batch)"
    parts = []
    for i, r in enumerate(research_notes, 1):
        parts.append(
            f"## {i}. {r['ticker']} (conviction {r.get('conviction', 0.5):.2f})\n\n"
            f"**Bull:** {r.get('bull_case', '—')}\n\n"
            f"**Bear:** {r.get('bear_case', '—')}\n\n"
            f"**Thesis:** {r.get('thesis_md', '—')}"
        )
    return "\n\n---\n\n".join(parts)


def call_anthropic_construction(
    persona: PersonaId,
    research_payload: str,
    as_of: date,
    *,
    feedback: str | None = None,
) -> tuple[str, int, int, int, int]:
    """Returns (raw_text, tokens_in, tokens_out, cached_tokens, latency_ms).

    `feedback` is the verbatim error from the previous attempt's
    validation — appended to the prompt so the LLM sees what went wrong.
    Without it, the retry just regenerates the same kind of incoherent
    book.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set")

    client = Anthropic(api_key=settings.anthropic_api_key)
    persona_specs = load_persona_specs()
    system_prompt = persona_specs[persona]
    user_content = build_construction_prompt(persona, research_payload, as_of)
    if feedback:
        user_content = (
            f"{user_content}\n\n---\nYour previous output was rejected:\n"
            f"{feedback}\n\n"
            f"Rework the book to fix this specific issue. If positions + cash "
            f"summed > 1.0, size down — start by trimming the smallest "
            f"conviction names or capping the highest at less than "
            f"max_single_name. If < 1.0, add more positions from the research "
            f"notes (your shortlist had {research_payload.count('## ')} candidates), "
            f"or raise cash_target within range. Return ONLY the JSON object."
        )

    t0 = time.perf_counter()
    # max_tokens=16000: the construction output is structured JSON over
    # the full sized book (10-20 proposals for stock pickers), each with
    # a sizing-reasoning blurb. Cathie's 14-ticker batch on 2026-06-10
    # hit max_tokens=4096 mid-string, returning unparseable JSON. Sonnet
    # 4.6 supports up to 64k output tokens; 16k leaves headroom without
    # paying for tokens we don't use.
    resp = client.messages.create(
        model=settings.llm_model_thesis,
        max_tokens=16000,
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_content}],
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    raw = resp.content[0].text if resp.content else ""
    usage = resp.usage
    log.info(
        "anthropic_construction_ok",
        persona=persona,
        latency_ms=latency_ms,
        tokens_in=usage.input_tokens,
        tokens_out=usage.output_tokens,
        n_research_notes=research_payload.count("## "),
    )
    return raw, usage.input_tokens, usage.output_tokens, getattr(usage, "cache_read_input_tokens", 0) or 0, latency_ms


def construct_portfolio(
    persona: PersonaId,
    research_notes: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    persist: bool = True,
) -> AnalystReport:
    """Pass-2 construction call. Takes a list of research note dicts
    (each ~TickerResearch-shaped: ticker, conviction, thesis_md,
    bull_case, bear_case), produces an AnalystReport whose proposals +
    cash_target sum to 1.0 (Pydantic-enforced).
    """
    from tessera_worker.agents.anthropic_runner import (
        build_analyst_report,
        check_daily_budget,
        estimate_cost_usd,
        log_llm_call,
        parse_llm_json,
        persist_analyst_report,
    )
    from tessera_worker.db import session_scope

    settings = get_settings()
    if not settings.feature_real_llm:
        from tessera_worker.agents.anthropic_runner import LlmDisabledError
        raise LlmDisabledError("FEATURE_REAL_LLM=false")

    as_of = as_of or date.today()
    payload = format_research_payload(research_notes)
    constraints = constraints_for(persona)
    model = settings.llm_model_thesis

    with session_scope() as session:
        check_daily_budget(session)
        last_error: str | None = None
        for attempt in range(2):
            try:
                raw, tin, tout, cached, latency = call_anthropic_construction(
                    persona, payload, as_of,
                    feedback=last_error if attempt > 0 else None,
                )
                cost = estimate_cost_usd(model, tin, tout)
                parsed = parse_llm_json(raw)
                # Construction output doesn't carry citations (those live
                # on the research notes already on file).
                report = build_analyst_report(
                    parsed,
                    persona_id=persona,
                    as_of=as_of,
                    inputs_hash="construction-" + str(int(time.time())),
                    model=model,
                    tokens_in=tin,
                    tokens_out=tout,
                    cost_usd=cost,
                    allowed_news_ids=set(),
                )
                # ──────────────────────────────────────────────────────
                # Validation. The schema already enforces sum ≤ 1.0 as a
                # universal upper bound; this block adds the persona-
                # specific rules: cap, sector, cash range, AND the
                # strict-equality conservation check. Any violation
                # triggers a retry with the error in `last_error` —
                # `_retry_guidance_for` will tell the LLM how to fix.
                # ──────────────────────────────────────────────────────
                sum_positions = sum(p.target_weight for p in report.proposals)
                total = sum_positions + report.cash_target
                if abs(total - 1.0) > 0.01:
                    raise ValueError(
                        f"book sum {total:.4f} ≠ 1.0 — "
                        f"positions {sum_positions:.4f} + cash {report.cash_target:.4f}. "
                        f"Fill missing exposure with additional sized proposals "
                        f"or raise cash_target to absorb the gap (within range "
                        f"[{constraints.cash_min:.2f}, {constraints.cash_max:.2f}])."
                    )
                for p in report.proposals:
                    if p.target_weight > constraints.max_single_name + 1e-6:
                        raise ValueError(
                            f"{p.ticker} target_weight {p.target_weight:.4f} "
                            f"exceeds {persona}.max_single_name "
                            f"{constraints.max_single_name:.4f}"
                        )
                # Cash range
                if not (constraints.cash_min - 1e-6 <= report.cash_target <= constraints.cash_max + 1e-6):
                    raise ValueError(
                        f"cash_target {report.cash_target:.4f} outside "
                        f"{persona} range [{constraints.cash_min:.4f}, {constraints.cash_max:.4f}]"
                    )
                # Position count guidance — soft floor. If the LLM
                # underfilled the book within constraint cash range, it
                # almost always means it parsed "qualify for sizing" too
                # strictly. Surface the conflict instead of persisting a
                # 1-position book.
                n_active = sum(1 for p in report.proposals if p.target_weight > 1e-4)
                if n_active < constraints.target_position_count_min:
                    raise ValueError(
                        f"only {n_active} active positions, persona requires "
                        f"≥{constraints.target_position_count_min}. Either size more "
                        f"of the research candidates or revisit which ones cleared "
                        f"the conviction floor."
                    )
                log_llm_call(
                    session,
                    persona_id=persona,
                    stage="construction",
                    model=model,
                    tokens_in=tin,
                    tokens_out=tout,
                    cost_usd=cost,
                    latency_ms=latency,
                    success=True,
                    error=None,
                    cached_tokens=cached,
                )
                if persist:
                    persist_analyst_report(session, report, raw_response=raw)
                return report
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning("construction.attempt_failed",
                            persona=persona, attempt=attempt, error=last_error)
                if attempt == 0:
                    continue
                raise
    # Unreachable — the loop either returns or raises.
    raise RuntimeError(f"construction unreachable: {last_error}")


def research_to_payload_dict(research) -> dict[str, Any]:
    """Convert a TickerResearch instance to a plain dict suitable for
    `format_research_payload`. Handles both Pydantic model instances
    and already-dict shapes."""
    if hasattr(research, "model_dump"):
        d = research.model_dump()
    else:
        d = dict(research)
    return {
        "ticker": d.get("ticker"),
        "conviction": float(d.get("conviction") or 0.5),
        "thesis_md": d.get("thesis_md") or "",
        "bull_case": d.get("bull_case") or "",
        "bear_case": d.get("bear_case") or "",
    }


__all__ = [
    "build_construction_prompt",
    "call_anthropic_construction",
    "constraints_for",
    "construct_portfolio",
    "format_research_payload",
    "research_to_payload_dict",
]

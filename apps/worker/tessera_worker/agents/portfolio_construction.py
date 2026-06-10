"""Portfolio construction agent — second pass of the 2-pass persona flow.

THIS MODULE IS A STUB FOR THE NEXT PR. It declares the public surface
and the prompt template; the LLM-calling logic, persistence, and the
persona_batch rewire arrive in the follow-up PR so the changes can be
landed and reviewed in two reasonable-sized diffs.

# Two-pass overview

Until 2026-06-09 the worker used a single `run_thesis(persona, ticker)`
call per (persona, ticker) cell. Each call generated thesis prose AND
a `target_weight`, with zero visibility into sibling cells. The
aggregator at `/api/proposals/{personaId}` would deduplicate by ticker
and average the `cash_target` across cells — for stock-picker personas
the resulting book typically didn't sum to 1.0. Warren's batch on
06-09 sized 8% BRK.B + 9 × 0% + 12% cash = 20% allocated; PR #76
patched the aggregator to infer the missing 80% as cash. That's a
bandage, not the right architecture.

Human analysts don't work that way. They research each candidate
individually, THEN sit down and decide relative sizing across the full
set. The 2-pass design mirrors that:

  Pass 1 — RESEARCH  (per ticker, runs in parallel across cells)
    Input:  persona prompt + ticker features + recent news
    Output: TickerResearch {
              ticker, conviction (0..1), thesis_md,
              bull_case, bear_case,
              what_would_make_me_wrong
            }
    Lighter than the old run_thesis — no `target_weight`, no
    `cash_target`, no `side`. Pure judgment on this one name.

  Pass 2 — CONSTRUCTION  (one call per persona per batch)
    Input:  persona prompt
            + all pass-1 TickerResearch from this batch
            + persona_constraints.PortfolioConstraints
              (max_single_name, max_sector, cash range,
               conviction thresholds, target position count)
    Output: AnalystReport {
              proposals[],  ← each one a real sized position
              cash_target,
              watchlist[],  ← named but unsized; carries the
                              research blurb so the UI can still
                              show "we looked at this and passed"
            }
    Constraint: proposals + cash_target = 1.0  (Pydantic enforces).

The construction call gets to do the relative-comparison thinking the
single-cell call never could: "MSFT 9/10 vs MCO 7/10 → size MSFT
heavier, leave MCO at small or watchlist." It also enforces the
persona's hard caps inside the same act of judgment, which means the
Phase-C risk gateway shrinks from "reject + retry" to "validate the
construction output against the same numbers."

# Status

- Constraints registry: shipped (`persona_constraints.py`).
- Prompt template: drafted below.
- TickerResearch schema: NOT YET. See packages/shared/tessera_shared/schemas.py
  follow-up. The construction prompt below references it by shape.
- Construction caller (`construct_portfolio`): STUB only. Raises
  NotImplementedError. Wires to anthropic_runner in the next PR.
- persona_batch rewire: NOT YET. Still calls run_thesis per cell.

# Cost note

Construction call is one shot per persona per batch, with research
notes as input context (~10-15 names × ~200 tokens summary each =
~2-3K tokens in) and a structured portfolio JSON out (~1K tokens
out). At Sonnet rates ≈ $0.08/call. Across 4 personas weekly:
~$0.32/week. Research calls drop ~$0.02 each by losing the sizing
section. Net cost: roughly flat with the previous single-pass flow,
buys coherent books in exchange.
"""

from __future__ import annotations

from datetime import date

from tessera_worker.agents.persona_constraints import (
    PersonaId,
    constraints_for,
    constraints_prompt_block,
)


def build_construction_prompt(
    persona: PersonaId,
    research_payload: str,
    as_of: date,
) -> str:
    """Assemble the user-content block for the construction call.

    `research_payload` is the rendered Pass-1 research output for ALL
    candidates this batch — a numbered list of `TickerResearch` blocks.
    The persona's operational prompt (voice + philosophy) is loaded
    separately and goes in the system block; this is the user-side
    portfolio-construction brief.
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

Return a JSON object with this shape:

  {{
    "cash_target": <fraction>,
    "proposals": [
      {{
        "ticker": "<symbol from the research notes>",
        "side": "buy" | "hold" | "trim" | "add",
        "target_weight": <fraction>,
        "horizon_days": <int, persona's typical hold>,
        "conviction": <0..1, copied from the research note>,
        "thesis_md": "<one-paragraph SIZING reasoning — why THIS weight, "
                     "vs the other candidates. Reference relative conviction "
                     "and how this name slots against the cap envelope. "
                     "Do NOT restate the full research thesis; that's already on file.>"
      }}
    ],
    "watchlist": [
      {{
        "ticker": "<symbol>",
        "reasoning": "<one sentence: what we'd need to see to size>"
      }}
    ],
    "notes_to_manager": "<2-3 sentences on what the book reflects this week>"
  }}

Active proposals + cash_target MUST sum to exactly 1.0. Watchlist
entries carry zero weight by definition — they're named for the
record, not allocated NAV.

Size the strongest convictions first, then taper. When two candidates
have similar conviction scores, prefer the one with cleaner
fundamentals or better recent momentum — your judgment.
"""


def construct_portfolio(
    persona: PersonaId,
    research_payload: str,
    *,
    as_of: date | None = None,
    persist: bool = True,
):
    """Stub. Wires to anthropic_runner in the follow-up PR.

    Will mirror `run_thesis()`'s shape: call_anthropic_construction →
    parse_llm_json → schema validation (AnalystReport already enforces
    cash + weights ≤ 1.0; we'll tighten to == 1.0 ± 0.001 inside the
    aggregator) → persist single row per persona per batch.
    """
    raise NotImplementedError(
        "construct_portfolio: shipped in the follow-up PR. "
        "Constraints + prompt + design are landed in this PR for review."
    )


# Re-export for convenience so callers don't reach into persona_constraints
# directly. The constraint registry is THE place to edit per-persona caps.
__all__ = [
    "build_construction_prompt",
    "constraints_for",
    "construct_portfolio",
]

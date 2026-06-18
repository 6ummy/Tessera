"""Warren | AAPL prompt-assembly demo (no Anthropic call).

Run:  python -m tessera_worker.agents.demo_warren_aapl
See:  agents/LLM_pipeline_demo.md
"""

from __future__ import annotations

import contextlib
import sys
from datetime import date

from tessera_worker.agents.models import PersonaId
from tessera_worker.agents.prompt_assembler import (
    RENDER_RULES,
    assemble_prompt,
    build_user_message,
    fetch_inputs,
    render_features,
    render_filing,
    render_fundamentals,
    render_fundamentals_trend,
    render_macros,
    render_news,
    render_price_history,
)
from tessera_worker.db import session_scope

with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

TICKER = "AAPL"
PERSONA: PersonaId = "warren"


def main() -> int:
    print(f"\n=== {PERSONA} | {TICKER} | {date.today()} ===\n")
    with session_scope() as session:
        blocks = fetch_inputs(session, PERSONA, TICKER)
        assembled = assemble_prompt(PERSONA, TICKER, session=session)

    print(render_features(blocks["features"]))
    print()
    if RENDER_RULES[PERSONA]["include_price_history"]:
        print(render_price_history(blocks["prices_full"]))
        print()
    print(render_fundamentals(blocks["fundamentals"]))
    print()
    print(render_fundamentals_trend(blocks["fundamentals_annual"]))
    print()
    print(render_macros(blocks["macros"]))
    print()
    if blocks.get("memory"):
        print(blocks["memory"])
        print()
    print(render_news(blocks["news"]))
    print()
    print(render_filing(blocks["filing"]))
    print()

    user_msg = build_user_message(PERSONA, TICKER, blocks)
    est_tokens = len(user_msg) // 4
    print("-" * 72)
    print(f"--- assembled user message (~{est_tokens:,} tokens) ---")
    print(f"--- system prompt: {len(assembled.system_prompt):,} chars (persona_loader) ---")
    print("-" * 72)
    print(user_msg)
    print()
    print("Next: FEATURE_REAL_LLM=true + ANTHROPIC_API_KEY →")
    print("  python -m tessera_worker.agents.anthropic_runner warren AAPL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

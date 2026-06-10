"""Dump the latest analyst_reports row's parsed JSON for one persona.

Usage:
    .venv\\Scripts\\python.exe scripts\\dump_latest_proposal.py cathie
"""
from __future__ import annotations

import json
import sys

from sqlalchemy import text

from tessera_worker.db import session_scope


def main(persona: str = "cathie") -> int:
    with session_scope() as s:
        row = s.execute(
            text("""
                SELECT ts, parsed
                FROM analyst_reports
                WHERE persona_id = :p
                ORDER BY ts DESC
                LIMIT 1
            """),
            {"p": persona},
        ).first()

    if not row:
        print(f"(no rows for {persona})")
        return 1

    ts, parsed_raw = row
    parsed = parsed_raw if isinstance(parsed_raw, dict) else json.loads(parsed_raw)

    print(f"=== {persona} @ {ts} ===\n")
    print(f"cash_target: {parsed.get('cash_target')}")
    print(f"notes_to_manager: {(parsed.get('notes_to_manager') or '')[:200]}")
    print()
    proposals = parsed.get("proposals", []) or []
    print(f"proposals ({len(proposals)}):")
    total = 0.0
    for p in proposals:
        ticker = p.get("ticker") or "—"
        weight = p.get("target_weight", 0.0)
        conv = p.get("conviction", 0.0)
        side = p.get("side", "—")
        total += float(weight or 0.0)
        print(f"  {ticker:10s}  weight={weight:.3f}  conv={conv:.2f}  side={side}")
    print()
    cash = float(parsed.get("cash_target") or 0.0)
    print(f"sum positions: {total:.4f}")
    print(f"sum + cash:    {total + cash:.4f}")
    return 0


if __name__ == "__main__":
    persona = sys.argv[1] if len(sys.argv) > 1 else "cathie"
    sys.exit(main(persona))

"""Hallucination canary — invariant checks on the most recent batch's outputs.

Designed to run weekly as the LAST step of the cron, after persona_batch.py.
Reads the most-recent `run_id` from `backtest_reports` (or `analyst_reports`
in prod-batch mode) and asserts five quality invariants:

  1. **Every cited_news_ids resolves** to a real `news` row.
     Citation validator already enforces this on write, but a row could land
     before the validator (race / bug). Belt + suspenders.

  2. **No mode-collapse anchoring** — no Proposal.target_weight ≥ 0.19
     (cap is 0.20). Per Plan.md §11: "model treats 18% cap as max-conviction
     default, producing portfolios with 4–5 names all at 17–18%."

  3. **Buy/add side requires conviction ≥ persona floor.** Warren ≥ 0.55,
     Cathie ≥ 0.50, Peter ≥ 0.50, Ray N/A (regime schema). Catches
     "I'm not sure but let's buy anyway" outputs.

  4. **No forbidden compliance phrases** in thesis_md
     ("guaranteed", "can't lose", "risk-free", "insider", "tip from",
     "sure thing"). Marketing/legal red lines.

  5. **No options/leverage talk in value/GARP voices** (Warren, Peter).
     Their specs exclude derivatives; if thesis_md mentions "calls", "puts",
     "leveraged", "margin loan", "options strategy" it's spec drift.

Exit code 0 = pass, 1 = fail (with reason summary).
Sentry capture on failure. Cron should treat exit 1 as STOP-THE-WORLD —
skip the next persona_batch run, alert on-call.

CLI:
  python -m tessera_worker.jobs.hallucination_canary --latest
  python -m tessera_worker.jobs.hallucination_canary --run-id <uuid>
  python -m tessera_worker.jobs.hallucination_canary --table analyst_reports
  python -m tessera_worker.jobs.hallucination_canary --since 2026-06-01
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


# ─────────────────────────────────────────────────────────────────────────
# Persona-specific thresholds
#
# Values pulled from personalities.md ("min_conviction" / "max_single_name"
# language in each persona's spec). Hardcoded here for the pilot — Phase C
# Risk Gateway will read these from `personas` table metadata once the
# Persona instances land in code.
# ─────────────────────────────────────────────────────────────────────────
PERSONA_MIN_BUY_CONVICTION: dict[str, float] = {
    "warren": 0.55,
    "cathie": 0.50,
    "peter":  0.50,
    # Ray uses RegimeReport (asset-class allocations), no per-proposal conviction
}

# 0.20 is the schema-level Proposal.target_weight cap. 0.19 buffer catches
# the anchoring failure mode without flagging legitimately-large positions.
CAP_ANCHOR_THRESHOLD = 0.19

# Compliance / marketing language that must NEVER appear in a thesis.
FORBIDDEN_PHRASES: list[str] = [
    "guaranteed return",
    "guaranteed profit",
    "can't lose",
    "cannot lose",
    "risk-free",
    "risk free",
    "insider info",
    "insider tip",
    "tip from",
    "sure thing",
    "easy money",
    "no downside",
]

# Per-persona forbidden topics. Value personas (Warren, Peter) shouldn't
# discuss options / leverage / margin loans even rhetorically; that's
# spec drift and a leading indicator the LLM is sliding off-persona.
PERSONA_FORBIDDEN_TOPICS: dict[str, list[str]] = {
    "warren": ["leveraged", "margin loan", "options strategy", "covered call",
               "naked call", "put spread", "selling puts"],
    "peter":  ["leveraged", "margin loan", "options strategy"],
}


# ─────────────────────────────────────────────────────────────────────────
# Result + violation types
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class Violation:
    check: str
    row_id: str
    persona: str
    ticker: str | None
    detail: str


@dataclass
class CanaryResult:
    rows_checked: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    def by_check(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.violations:
            counts[v.check] = counts.get(v.check, 0) + 1
        return counts


# ─────────────────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────────────────


def load_recent_rows(
    session,
    *,
    table: str = "backtest_reports",
    run_id: str | None = None,
    since: date | None = None,
) -> list[dict]:
    """Pull rows to check. Default = most recent run_id from backtest_reports.

    `analyst_reports` doesn't have a `run_id` column (prod theses are
    per-(persona, as_of_date) singletons), so `--table analyst_reports`
    requires `--since` instead.
    """
    if table == "backtest_reports":
        if run_id:
            sql = text("""
                SELECT id::text AS id, persona_id, parsed
                FROM backtest_reports
                WHERE run_id = :rid AND rejected = false
            """)
            params = {"rid": run_id}
        else:
            sql = text("""
                SELECT id::text AS id, persona_id, parsed
                FROM backtest_reports
                WHERE run_id = (
                    SELECT run_id FROM backtest_reports
                    ORDER BY created_at DESC LIMIT 1
                ) AND rejected = false
            """)
            params = {}
    elif table == "analyst_reports":
        cutoff = since or date.today()
        sql = text("""
            SELECT id::text AS id, persona_id, parsed
            FROM analyst_reports
            WHERE as_of_date >= :since AND rejected = false
        """)
        params = {"since": cutoff}
    else:
        raise ValueError(f"unknown table: {table}")

    rows = session.execute(sql, params).all()
    return [
        {
            "id": r.id,
            "persona_id": r.persona_id,
            "parsed": r.parsed if isinstance(r.parsed, dict) else json.loads(r.parsed),
        }
        for r in rows
    ]


def load_valid_news_ids(session) -> set[str]:
    rows = session.execute(text("SELECT id::text AS id FROM news")).all()
    return {r.id for r in rows}


# ─────────────────────────────────────────────────────────────────────────
# Individual invariant checks. Each takes (rows, *aux) and appends to
# `result.violations`. Pure-data — no DB access inside.
# ─────────────────────────────────────────────────────────────────────────


def check_citations_resolve(rows: list[dict], valid_ids: set[str],
                             result: CanaryResult) -> None:
    for r in rows:
        for prop in (r["parsed"].get("proposals") or []):
            cited = prop.get("cited_news_ids") or []
            for cite in cited:
                cite_str = str(cite)
                if cite_str not in valid_ids:
                    result.violations.append(Violation(
                        check="citation_resolves",
                        row_id=r["id"], persona=r["persona_id"],
                        ticker=prop.get("ticker"),
                        detail=f"cited news_id {cite_str} not in news table",
                    ))


def check_no_cap_anchoring(rows: list[dict], result: CanaryResult) -> None:
    for r in rows:
        for prop in (r["parsed"].get("proposals") or []):
            try:
                tw = float(prop.get("target_weight", 0))
            except (TypeError, ValueError):
                continue
            if tw >= CAP_ANCHOR_THRESHOLD:
                result.violations.append(Violation(
                    check="no_cap_anchoring",
                    row_id=r["id"], persona=r["persona_id"],
                    ticker=prop.get("ticker"),
                    detail=f"target_weight={tw:.4f} ≥ {CAP_ANCHOR_THRESHOLD} "
                           f"(possible mode-collapse at 0.20 cap)",
                ))


def check_buy_conviction_floor(rows: list[dict], result: CanaryResult) -> None:
    for r in rows:
        persona = r["persona_id"]
        floor = PERSONA_MIN_BUY_CONVICTION.get(persona)
        if floor is None:
            continue
        for prop in (r["parsed"].get("proposals") or []):
            side = (prop.get("side") or "").lower()
            if side not in ("buy", "add"):
                continue
            try:
                conv = float(prop.get("conviction", 0))
            except (TypeError, ValueError):
                continue
            if conv < floor:
                result.violations.append(Violation(
                    check="buy_conviction_floor",
                    row_id=r["id"], persona=persona,
                    ticker=prop.get("ticker"),
                    detail=f"side={side} but conviction={conv:.2f} < floor {floor}",
                ))


def check_forbidden_phrases(rows: list[dict], result: CanaryResult) -> None:
    # Compile once, case-insensitive whole-phrase match.
    patterns = [(p, re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE))
                for p in FORBIDDEN_PHRASES]
    for r in rows:
        for prop in (r["parsed"].get("proposals") or []):
            text_md = prop.get("thesis_md") or ""
            for phrase, pat in patterns:
                if pat.search(text_md):
                    result.violations.append(Violation(
                        check="forbidden_phrase",
                        row_id=r["id"], persona=r["persona_id"],
                        ticker=prop.get("ticker"),
                        detail=f"phrase {phrase!r} found in thesis_md",
                    ))


def check_persona_topic_drift(rows: list[dict], result: CanaryResult) -> None:
    """Value/GARP voices shouldn't talk options/leverage — spec drift signal."""
    compiled = {
        persona: [(t, re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE))
                  for t in topics]
        for persona, topics in PERSONA_FORBIDDEN_TOPICS.items()
    }
    for r in rows:
        persona = r["persona_id"]
        if persona not in compiled:
            continue
        for prop in (r["parsed"].get("proposals") or []):
            text_md = prop.get("thesis_md") or ""
            for topic, pat in compiled[persona]:
                if pat.search(text_md):
                    result.violations.append(Violation(
                        check="persona_topic_drift",
                        row_id=r["id"], persona=persona,
                        ticker=prop.get("ticker"),
                        detail=f"{persona!r} thesis mentioned {topic!r}",
                    ))


# ─────────────────────────────────────────────────────────────────────────
# Top-level runner
# ─────────────────────────────────────────────────────────────────────────


def run_canary(
    session, *, table: str = "backtest_reports",
    run_id: str | None = None, since: date | None = None,
) -> CanaryResult:
    result = CanaryResult()
    rows = load_recent_rows(session, table=table, run_id=run_id, since=since)
    result.rows_checked = len(rows)
    if not rows:
        log.warning("canary.no_rows_found",
                    table=table, run_id=run_id, since=str(since) if since else None)
        return result
    valid_news = load_valid_news_ids(session)

    check_citations_resolve(rows, valid_news, result)
    check_no_cap_anchoring(rows, result)
    check_buy_conviction_floor(rows, result)
    check_forbidden_phrases(rows, result)
    check_persona_topic_drift(rows, result)
    return result


def print_summary(result: CanaryResult) -> None:
    print()
    print(f"=== Hallucination canary ===")
    print(f"  rows checked: {result.rows_checked}")
    print(f"  violations:   {len(result.violations)}")
    if result.violations:
        print(f"  by check:")
        for check, n in sorted(result.by_check().items()):
            print(f"    {check}: {n}")
        print()
        print(f"  first {min(10, len(result.violations))} violations:")
        for v in result.violations[:10]:
            t = v.ticker or "-"
            print(f"    [{v.check}] {v.persona} x {t} (row {v.row_id[:8]}): {v.detail}")
    print()
    verdict = "PASS" if result.passed else "FAIL — stop the world"
    print(f"  Verdict: {verdict}")


def main() -> int:
    p = argparse.ArgumentParser(description="Tessera LLM hallucination canary")
    p.add_argument("--table", choices=("backtest_reports", "analyst_reports"),
                   default="backtest_reports")
    p.add_argument("--run-id", type=str, default=None,
                   help="Specific run_id (backtest_reports only). Default: latest.")
    p.add_argument("--since", type=str, default=None,
                   help="YYYY-MM-DD cutoff (analyst_reports only).")
    p.add_argument("--latest", action="store_true",
                   help="Explicitly request latest run (default behavior).")
    args = p.parse_args()

    since = date.fromisoformat(args.since) if args.since else None

    with session_scope() as session:
        result = run_canary(session, table=args.table,
                            run_id=args.run_id, since=since)

    print_summary(result)

    if not result.passed:
        # Surface to Sentry — worker already initializes Sentry SDK at startup.
        try:
            import sentry_sdk
            sentry_sdk.capture_message(
                f"hallucination_canary FAILED — {len(result.violations)} "
                f"violations across {result.rows_checked} rows",
                level="error",
                extras={"by_check": result.by_check(),
                        "first_violations": [
                            {"check": v.check, "persona": v.persona,
                             "ticker": v.ticker, "detail": v.detail}
                            for v in result.violations[:10]
                        ]},
            )
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

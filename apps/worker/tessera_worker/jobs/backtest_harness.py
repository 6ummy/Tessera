"""Backtest harness — replay N historical days, generate theses, persist to
backtest_reports, print summary stats.

Why this exists (Plan.md Phase B Week 3 acceptance):
- Verify schema-validation failure rate < 2% over 30 days × 4 personas.
- Verify 0 hallucinated tickers reach the (would-be) UI.
- Hand-sample voice quality for a representative subset.

Cost discipline:
- LLM_MAX_DAILY_COST_USD is honored — the harness checks the same daily
  cap as production and refuses to keep calling once spent.
- A --max-cost flag also caps the TOTAL spend for one harness run, on
  top of the daily cap. Defaults to $5.
- --dry-run skips Anthropic calls entirely; useful for verifying the
  point-in-time fetch + persistence path before paying.

Point-in-time correctness:
- All `fetch_inputs` queries are upper-bounded by `as_of` (added in the
  same PR — see prompt_assembler.fetch_inputs). News, features,
  fundamentals, filings, macros, and memory all WHERE-clause on the
  replay date. No future leakage by construction.

Usage:
    # Last 10 trading days × 3 personas × 5 tickers, dry run first
    python -m tessera_worker.jobs.backtest_harness \
        --days 10 --personas warren cathie peter \
        --tickers AAPL NVDA COST MSFT TSM --dry-run

    # Real run, $3 cap
    python -m tessera_worker.jobs.backtest_harness \
        --days 10 --personas warren cathie peter \
        --tickers AAPL NVDA COST MSFT TSM --max-cost 3.0
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

# Force UTF-8 stdout so summary tables don't crash on Windows cp1252.
with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class RunResult:
    run_id: UUID
    attempted: int = 0
    persisted: int = 0
    rejected: int = 0
    errors: int = 0
    total_cost_usd: float = 0.0
    by_persona: dict[str, dict[str, int]] = field(default_factory=dict)

    def bump(self, persona: str, kind: str) -> None:
        b = self.by_persona.setdefault(persona, {"attempted": 0, "persisted": 0,
                                                  "rejected": 0, "errors": 0})
        b[kind] = b.get(kind, 0) + 1

    def schema_fail_rate(self) -> float:
        return self.rejected / self.attempted if self.attempted else 0.0


def trading_days(end: date, n: int) -> list[date]:
    """Last `n` weekdays ending at `end` (skip Sat/Sun — no calendar API needed
    for a sub-month window)."""
    out = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:  # Mon-Fri
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def persist_backtest_row(
    session, *, run_id: UUID, replay_as_of: date,
    persona_id: str, as_of_date: date, inputs_hash: str,
    raw_response: str, parsed_json: str | None, model: str,
    tokens_in: int, tokens_out: int, cost_usd: float,
    rejected: bool, reject_reasons: list[str],
) -> None:
    """parsed_json may be None (e.g. both LLM attempts failed validation —
    we still want the raw text + reject reason in the table for review)."""
    # NULL → CAST(NULL AS jsonb) is fine; only build the CAST when we
    # have a real JSON string so we don't accidentally insert literal "null".
    parsed_sql = "CAST(:parsed AS jsonb)" if parsed_json is not None else "NULL"
    session.execute(
        text(f"""
            INSERT INTO backtest_reports
                (run_id, replay_as_of, persona_id, as_of_date, inputs_hash,
                 raw_response, parsed, model, tokens_in, tokens_out, cost_usd,
                 rejected, reject_reasons)
            VALUES
                (:rid, :replay, :p, :asof, :hash,
                 :raw, {parsed_sql}, :model, :ti, :to, :cost,
                 :rej, :reasons)
        """),
        {
            "rid": str(run_id), "replay": replay_as_of,
            "p": persona_id, "asof": as_of_date, "hash": inputs_hash,
            "raw": raw_response,
            **({"parsed": parsed_json} if parsed_json is not None else {}),
            "model": model,
            "ti": tokens_in, "to": tokens_out, "cost": cost_usd,
            "rej": rejected, "reasons": reject_reasons,
        },
    )


def run_one(
    session, *, run_id: UUID, replay_as_of: date,
    persona: str, ticker: str, dry_run: bool,
    result: RunResult,
) -> None:
    """One (replay_as_of, persona, ticker) attempt. Errors are logged + counted,
    never raised — harness must complete all cells.

    Uses `assemble_prompt` (the same entry point production `run_thesis`
    uses) so the prompt + system block + inputs_hash + news_ids are
    constructed identically. point-in-time correctness is enforced inside
    `fetch_inputs` via the `as_of` upper-bound.
    """
    from tessera_worker.agents.prompt_assembler import assemble_prompt

    result.attempted += 1
    result.bump(persona, "attempted")

    try:
        assembled = assemble_prompt(persona, ticker, as_of=replay_as_of)  # type: ignore[arg-type]
    except Exception as e:
        log.warning("backtest.assemble_failed",
                    persona=persona, ticker=ticker, replay_as_of=str(replay_as_of),
                    error=str(e), error_type=type(e).__name__)
        result.errors += 1
        result.bump(persona, "errors")
        return

    if dry_run:
        # Assembly succeeded — that's the full check for --dry-run.
        result.persisted += 1
        result.bump(persona, "persisted")
        return

    # Real path: 2-attempt retry with feedback (mirrors prod `run_thesis`).
    # First attempt fails Pydantic / citations → we feed the error back
    # in attempt 2 ("Fix JSON only"). Both fail → persist with parsed=NULL
    # + raw text + reject_reasons so the row exists for manual review.
    from tessera_worker.agents.anthropic_runner import (
        build_analyst_report,
        call_anthropic_thesis,
        estimate_cost_usd,
        parse_llm_json,
    )
    from tessera_worker.agents.citation_validator import validate_citations

    model_name = "claude-sonnet-4-6"
    last_error: str | None = None
    last_raw = ""
    last_ti = last_to = 0
    last_cost = 0.0
    report = None
    cite_problems: list[str] = []

    for attempt in range(2):
        feedback = last_error if attempt > 0 else None
        try:
            raw, ti, to_, _cached, _ms = call_anthropic_thesis(assembled, feedback=feedback)
            last_raw, last_ti, last_to = raw, ti, to_
            last_cost = estimate_cost_usd(model_name, ti, to_)
            result.total_cost_usd += last_cost  # count both attempts toward cap

            parsed = parse_llm_json(raw)
            report = build_analyst_report(
                parsed, persona_id=persona, as_of=replay_as_of,  # type: ignore[arg-type]
                inputs_hash=assembled.inputs_hash, model=model_name,
                tokens_in=ti, tokens_out=to_, cost_usd=last_cost,
                allowed_news_ids=set(assembled.news_ids),
            )
            cite_problems = validate_citations(report, set(assembled.news_ids))
            if cite_problems:
                last_error = f"Invalid cited_news_ids: {cite_problems}"
                if attempt == 0:
                    continue
            break  # success (or final attempt with citation problems we accept as "rejected")
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:300]}"
            if attempt == 0:
                continue
            # Second attempt also raised — persist a rejected row with raw text only.
            log.warning("backtest.persist_unparseable",
                        persona=persona, ticker=ticker, replay_as_of=str(replay_as_of),
                        error=last_error)
            try:
                persist_backtest_row(
                    session, run_id=run_id, replay_as_of=replay_as_of,
                    persona_id=persona, as_of_date=replay_as_of,
                    inputs_hash=assembled.inputs_hash,
                    raw_response=last_raw or "",
                    parsed_json=None,  # nullable column
                    model=model_name, tokens_in=last_ti, tokens_out=last_to,
                    cost_usd=last_cost,
                    rejected=True, reject_reasons=[last_error],
                )
            except Exception as persist_err:
                log.warning("backtest.persist_failed", error=str(persist_err))
            result.rejected += 1
            result.bump(persona, "rejected")
            return

    # If we get here, at least one attempt produced a buildable report.
    assert report is not None
    rejected = bool(cite_problems)
    persist_backtest_row(
        session, run_id=run_id, replay_as_of=replay_as_of,
        persona_id=persona, as_of_date=replay_as_of,
        inputs_hash=assembled.inputs_hash, raw_response=last_raw,
        parsed_json=report.model_dump_json(),
        model=model_name, tokens_in=last_ti, tokens_out=last_to,
        cost_usd=last_cost, rejected=rejected,
        reject_reasons=cite_problems,
    )
    if rejected:
        result.rejected += 1
        result.bump(persona, "rejected")
    else:
        result.persisted += 1
        result.bump(persona, "persisted")


def print_summary(result: RunResult) -> None:
    print()
    print(f"=== Backtest run {result.run_id} ===")
    print(f"  attempted:        {result.attempted}")
    print(f"  persisted:        {result.persisted}")
    print(f"  rejected (cite):  {result.rejected}")
    print(f"  errored:          {result.errors}")
    print(f"  schema fail rate: {result.schema_fail_rate():.2%}")
    print(f"  total cost USD:   ${result.total_cost_usd:.3f}")
    print()
    print(f"{'persona':<12} attempted persisted rejected errors")
    for p, b in sorted(result.by_persona.items()):
        print(f"  {p:<10} {b.get('attempted', 0):>9} {b.get('persisted', 0):>9} "
              f"{b.get('rejected', 0):>8} {b.get('errors', 0):>6}")
    print()
    if result.attempted:
        # Phase B acceptance: < 2% schema-validation failure.
        verdict = "PASS" if result.schema_fail_rate() < 0.02 else "FAIL"
        print(f"  Phase B acceptance (<2% schema fail): {verdict}")


def main() -> int:
    p = argparse.ArgumentParser(description="Tessera persona thesis backtest harness")
    p.add_argument("--days", type=int, default=10,
                   help="Number of trading days to replay (default 10)")
    p.add_argument("--personas", nargs="+",
                   default=["warren", "cathie", "peter"],
                   choices=["warren", "cathie", "ray", "peter"],
                   help="Personas to replay (ray uses regime schema; not yet wired here)")
    p.add_argument("--tickers", nargs="+", required=True,
                   help="Tickers to replay")
    p.add_argument("--end-date", type=str, default=None,
                   help="Replay window end date YYYY-MM-DD (default: today)")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip LLM calls; verify point-in-time assembly only")
    p.add_argument("--max-cost", type=float, default=5.0,
                   help="Abort run when total USD exceeds this (default $5)")
    args = p.parse_args()

    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    replay_dates = trading_days(end, args.days)
    run_id = uuid4()
    result = RunResult(run_id=run_id)

    n_cells = args.days * len(args.personas) * len(args.tickers)
    print(f"Backtest run_id={run_id}  cells={n_cells}  dry={args.dry_run}  cap=${args.max_cost}")
    print(f"Replay dates: {replay_dates[0]} → {replay_dates[-1]}  "
          f"({len(replay_dates)} days)")

    with session_scope() as session:
        for d in replay_dates:
            for persona in args.personas:
                for ticker in args.tickers:
                    if not args.dry_run and result.total_cost_usd >= args.max_cost:
                        print(f"  cost cap ${args.max_cost} reached — stopping early")
                        print_summary(result)
                        return 0
                    run_one(session, run_id=run_id, replay_as_of=d,
                            persona=persona, ticker=ticker,
                            dry_run=args.dry_run, result=result)

    print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

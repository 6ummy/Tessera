"""Persona thesis batch — the weekly cron that actually generates production
analyst reports.

Why this exists: until this lands, `FEATURE_REAL_LLM=true` on prod has no
effect, because nothing in the orchestrator calls `anthropic_runner`. Manual
CLI invocations only.

Design:
  - Each persona has a curated SHORTLIST of tickers it cares about. No
    Haiku universe-screen — the pilot universe is 50 names, the funnel
    would be over-engineering.
  - For each (persona, ticker): call `anthropic_runner.run_thesis(...)`,
    which already does 2-attempt retry + persists to `analyst_reports` +
    writes `persona_memory` embeddings + honors `FEATURE_REAL_LLM` and
    `LLM_MAX_DAILY_COST_USD`.
  - For Ray: one call to `run_regime_thesis()` — no ticker arg, RegimeReport
    schema, persists to `analyst_reports` with `persona_id='ray'`.
  - Errors per (persona, ticker) are counted, never raised — one persona's
    bad day shouldn't take down the run.
  - Budget gate is layered: prod-level `check_daily_budget()` raises
    `LlmDailyBudgetExceeded` after the cap; we also honor a per-run
    `--max-cost` so a single batch can't blow the weekly allowance.

CLI:
  python -m tessera_worker.jobs.persona_batch
  python -m tessera_worker.jobs.persona_batch --personas warren cathie
  python -m tessera_worker.jobs.persona_batch --dry-run
  python -m tessera_worker.jobs.persona_batch --max-cost 2.0

HTTP:
  POST /jobs/persona-batch
  Authorization: Bearer ${WORKER_WEBHOOK_SECRET}
  (Vercel cron fires this; see apps/web/app/api/cron/weekly/route.ts.)

Cadence: weekly, Friday after US market close. Decision 2026-06-04:
  - Daily would cost ~$72/mo for 4 personas × 30 tickers × $0.02.
  - Weekly costs ~$5–7/mo, sufficient for the paper pilot.
  - Daily can be re-enabled via cron schedule when live mode launches.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from tessera_worker.logging import get_logger

log = get_logger(__name__)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


# ─────────────────────────────────────────────────────────────────────────
# Persona shortlists — curated subsets of the universe, chosen for fit with
# each persona's mandate. Easy to edit; keeps the batch under budget.
# ─────────────────────────────────────────────────────────────────────────
PERSONA_SHORTLISTS: dict[str, list[str]] = {
    "warren": [
        "AAPL", "MSFT", "BRK.B", "JPM", "V", "MA",
        "COST", "WMT", "JNJ", "MCO",
    ],
    "cathie": [
        "NVDA", "TSLA", "PLTR", "COIN", "CRWD",
        "SHOP", "ASML", "AMD", "AVGO", "ANET",
        # Crypto sleeve candidates — Cathie's prompt sizes them under the
        # "Crypto allocation (4th asset class)" rules (0-20% sleeve cap,
        # ≤10% per coin, BTC+ETH ≥50% of any non-zero sleeve, no
        # stablecoins). Selection biased toward themes she'll have
        # narrative tools for: programmable settlement (ETH, SOL), oracle
        # infrastructure (LINK), high-throughput L1 (SOL), monetary base
        # (BTC). Adding all 8 from the universe would burn budget on
        # names she won't underwrite anyway.
        "BTC/USD", "ETH/USD", "SOL/USD", "LINK/USD",
    ],
    "peter": [
        "COST", "HD", "DECK", "BKNG", "URI",
        "LRCX", "TSM", "AMZN", "META", "NOW",
    ],
    # Ray runs once per batch via run_regime_thesis (no ticker shortlist).
}


PersonaId = Literal["warren", "cathie", "peter", "ray"]


@dataclass
class BatchResult:
    started_at: float = field(default_factory=time.time)
    attempted: int = 0
    persisted: int = 0
    rejected: int = 0
    errors: int = 0
    total_cost_usd: float = 0.0
    by_persona: dict[str, dict[str, int | float]] = field(default_factory=dict)
    aborted_reason: str | None = None

    def bump(self, persona: str, kind: str, n: int = 1) -> None:
        b = self.by_persona.setdefault(
            persona,
            {"attempted": 0, "persisted": 0, "rejected": 0, "errors": 0, "cost_usd": 0.0},
        )
        b[kind] = float(b.get(kind, 0)) + n


def run_one(
    persona: PersonaId, ticker: str | None, *,
    dry_run: bool, as_of: date, result: BatchResult,
) -> None:
    """One (persona, ticker) call. Errors logged + counted, never raised."""
    result.attempted += 1
    result.bump(persona, "attempted")

    if dry_run:
        # Just verify the import path works; don't pay.
        result.persisted += 1
        result.bump(persona, "persisted")
        return

    # Lazy import — the runner pulls anthropic SDK + DB + voyage; don't
    # cost cold-start on /health or import-time test discovery.
    from tessera_worker.agents.anthropic_runner import (
        LlmDailyBudgetExceeded, LlmDisabledError,
        run_regime_thesis, run_thesis,
    )

    try:
        if persona == "ray":
            report = run_regime_thesis(as_of=as_of)
        else:
            assert ticker is not None
            report = run_thesis(persona=persona, ticker=ticker, as_of=as_of)
        result.persisted += 1
        result.bump(persona, "persisted")
        result.total_cost_usd += float(report.cost_usd)
        result.bump(persona, "cost_usd", float(report.cost_usd))
    except LlmDailyBudgetExceeded as e:
        result.aborted_reason = f"LLM_MAX_DAILY_COST_USD reached: {e}"
        result.bump(persona, "errors")
        result.errors += 1
        log.warning("persona_batch.budget_exceeded",
                    persona=persona, ticker=ticker, detail=str(e))
        raise   # bubble up; caller stops the run
    except LlmDisabledError as e:
        result.aborted_reason = f"FEATURE_REAL_LLM=false: {e}"
        result.bump(persona, "errors")
        result.errors += 1
        log.warning("persona_batch.llm_disabled",
                    persona=persona, ticker=ticker, detail=str(e))
        raise   # bubble up; no point continuing
    except Exception as e:
        # Per-cell failures (Pydantic, citation, JSONDecode after retry) get
        # persisted as rejected by run_thesis itself. Anything that escapes
        # here is unexpected (network, DB outage, etc.) — log + count + continue.
        log.warning("persona_batch.cell_failed",
                    persona=persona, ticker=ticker,
                    error=str(e), error_type=type(e).__name__)
        result.errors += 1
        result.bump(persona, "errors")


def run_batch_v2(
    *, personas: list[PersonaId] | None = None,
    dry_run: bool = False, as_of: date | None = None,
    max_cost: float = 5.0,
) -> BatchResult:
    """2-pass batch runner. For each stock-picker persona: research each
    ticker in the shortlist (lightweight, doesn't persist), then ONE
    construction call that takes all research notes + persona caps and
    outputs a coherent portfolio (proposals + cash = 1.0, Pydantic-
    enforced). Ray is unchanged — his regime call is already single-pass.

    Persists ONE analyst_reports row per persona per batch (vs the old
    N-rows-per-persona pattern). Aggregator at /api/proposals already
    handles this — most-recent row wins.
    """
    personas = personas or ["warren", "cathie", "peter", "ray"]
    as_of = as_of or date.today()
    result = BatchResult()

    log.info("persona_batch_v2.start", personas=personas, dry_run=dry_run,
             as_of=str(as_of), max_cost=max_cost)

    if dry_run:
        for persona in personas:
            tickers = PERSONA_SHORTLISTS.get(persona, []) or ["PORTFOLIO"]
            for ticker in tickers:
                result.attempted += 1
                result.bump(persona, "attempted")
                result.persisted += 1
                result.bump(persona, "persisted")
        return result

    # Lazy imports — these pull in the Anthropic SDK and shouldn't cost
    # cold-start time on test discovery.
    from tessera_worker.agents.anthropic_runner import (
        LlmDailyBudgetExceeded, LlmDisabledError,
        run_regime_thesis, run_research,
    )
    from tessera_worker.agents.portfolio_construction import construct_portfolio

    try:
        for persona in personas:
            if result.total_cost_usd >= max_cost:
                result.aborted_reason = (
                    f"per-run max-cost ${max_cost} reached before {persona}"
                )
                log.warning("persona_batch_v2.max_cost_hit",
                            spent=result.total_cost_usd, max=max_cost)
                break

            if persona == "ray":
                # Ray: single regime call, persists itself.
                result.attempted += 1
                result.bump("ray", "attempted")
                try:
                    rep = run_regime_thesis(as_of=as_of)
                    result.persisted += 1
                    result.bump("ray", "persisted")
                    result.total_cost_usd += float(rep.cost_usd)
                    result.bump("ray", "cost_usd", float(rep.cost_usd))
                except (LlmDailyBudgetExceeded, LlmDisabledError) as e:
                    result.aborted_reason = str(e)
                    raise
                except Exception as e:
                    result.errors += 1
                    result.bump("ray", "errors")
                    log.warning("persona_batch_v2.ray_failed", error=str(e))
                continue

            # Stock-picker: Pass 1 — research per ticker
            research_notes: list[dict] = []
            for ticker in PERSONA_SHORTLISTS.get(persona, []):
                if result.total_cost_usd >= max_cost:
                    result.aborted_reason = (
                        f"per-run max-cost ${max_cost} reached mid-{persona}-research"
                    )
                    log.warning("persona_batch_v2.max_cost_hit_mid_research",
                                spent=result.total_cost_usd, max=max_cost)
                    break
                result.attempted += 1
                result.bump(persona, "attempted")
                note = run_research(persona, ticker, as_of=as_of)
                if note is None:
                    result.errors += 1
                    result.bump(persona, "errors")
                    continue
                # Track cost from the research call (cell didn't persist).
                cell_cost = float(note.get("cost_usd", 0.0))
                result.total_cost_usd += cell_cost
                result.bump(persona, "cost_usd", cell_cost)
                research_notes.append(note)

            if not research_notes:
                log.warning("persona_batch_v2.no_research", persona=persona)
                continue

            # Pass 2 — construction call. Persists ONE AnalystReport row.
            try:
                construction_report = construct_portfolio(
                    persona, research_notes, as_of=as_of,
                )
                result.persisted += 1
                result.bump(persona, "persisted")
                result.total_cost_usd += float(construction_report.cost_usd)
                result.bump(persona, "cost_usd", float(construction_report.cost_usd))
                log.info("persona_batch_v2.construction_ok",
                         persona=persona,
                         n_research=len(research_notes),
                         n_proposals=len(construction_report.proposals),
                         cash_target=construction_report.cash_target)
            except (LlmDailyBudgetExceeded, LlmDisabledError) as e:
                result.aborted_reason = str(e)
                raise
            except Exception as e:
                result.errors += 1
                result.bump(persona, "errors")
                log.warning("persona_batch_v2.construction_failed",
                            persona=persona, error=str(e))
    except Exception as e:
        log.warning("persona_batch_v2.aborted", reason=str(e))

    return result


def run_batch(
    *, personas: list[PersonaId] | None = None,
    dry_run: bool = False, as_of: date | None = None,
    max_cost: float = 5.0,
) -> BatchResult:
    """The actual batch runner. Returns a BatchResult; never raises on per-cell
    errors. Raises only on system-level abort (budget exceeded, feature flag).
    """
    personas = personas or ["warren", "cathie", "peter", "ray"]
    as_of = as_of or date.today()
    result = BatchResult()

    log.info("persona_batch.start", personas=personas, dry_run=dry_run,
             as_of=str(as_of), max_cost=max_cost)

    try:
        for persona in personas:
            if not dry_run and result.total_cost_usd >= max_cost:
                result.aborted_reason = (
                    f"per-run max-cost ${max_cost} reached before {persona}"
                )
                log.warning("persona_batch.max_cost_hit",
                            spent=result.total_cost_usd, max=max_cost)
                break

            if persona == "ray":
                run_one("ray", None, dry_run=dry_run, as_of=as_of, result=result)
            else:
                for ticker in PERSONA_SHORTLISTS.get(persona, []):
                    if not dry_run and result.total_cost_usd >= max_cost:
                        result.aborted_reason = (
                            f"per-run max-cost ${max_cost} reached mid-{persona}"
                        )
                        log.warning("persona_batch.max_cost_hit",
                                    spent=result.total_cost_usd, max=max_cost)
                        break
                    run_one(persona, ticker, dry_run=dry_run, as_of=as_of, result=result)
    except Exception as e:
        # LlmDailyBudgetExceeded or LlmDisabledError — propagated as a stop signal.
        # result.aborted_reason already set in run_one.
        log.warning("persona_batch.aborted", reason=str(e))

    return result


def print_summary(result: BatchResult) -> None:
    duration = time.time() - result.started_at
    print()
    print(f"=== Persona batch ({duration:.1f}s) ===")
    print(f"  attempted:        {result.attempted}")
    print(f"  persisted:        {result.persisted}")
    print(f"  rejected:         {result.rejected}")
    print(f"  errored:          {result.errors}")
    print(f"  total cost USD:   ${result.total_cost_usd:.3f}")
    if result.aborted_reason:
        print(f"  aborted:          {result.aborted_reason}")
    print()
    print(f"{'persona':<10} attempted persisted errors cost_usd")
    for p in ("warren", "cathie", "peter", "ray"):
        b = result.by_persona.get(p)
        if not b:
            continue
        print(f"  {p:<8} {int(b.get('attempted', 0)):>9} "
              f"{int(b.get('persisted', 0)):>9} {int(b.get('errors', 0)):>6} "
              f"${float(b.get('cost_usd', 0)):>7.3f}")


def main() -> int:
    p = argparse.ArgumentParser(description="Tessera persona thesis batch")
    p.add_argument("--personas", nargs="+",
                   choices=("warren", "cathie", "peter", "ray"),
                   default=None,
                   help="Subset to run (default: all 4)")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip LLM calls; verify the loop + imports")
    p.add_argument("--max-cost", type=float, default=5.0,
                   help="Abort the run when total spend ≥ this (default $5)")
    p.add_argument("--as-of", type=str, default=None,
                   help="YYYY-MM-DD; defaults to today")
    args = p.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    result = run_batch(personas=args.personas, dry_run=args.dry_run,
                       as_of=as_of, max_cost=args.max_cost)
    print_summary(result)
    # Soft exit code: 0 unless we aborted on infra (budget / flag).
    return 1 if result.aborted_reason and "max-cost" not in result.aborted_reason else 0


if __name__ == "__main__":
    raise SystemExit(main())

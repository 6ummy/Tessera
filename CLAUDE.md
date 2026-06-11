# CLAUDE.md — instant catch-up for Claude Code sessions

## What this is

**Tessera**: 4 AI analyst personas (Warren=value, Cathie=disruptive growth
+crypto, Ray=macro regime allocator, Peter=GARP) write weekly Sonnet 4.6
investment theses over a shared market-data plane, and a paper engine
executes their books against $100K virtual accounts. Public repo, 5-person
team (정우 @6ummy owns coordination; CONTRIBUTING.md has the track map),
paper-trading pilot — **no real money, ever, without Phase E/F clearance**.

Monorepo: `apps/web` (Next.js 14, Vercel) · `apps/worker` (Python 3.11
FastAPI, Cloud Run `tessera-worker`, us-east1) · `packages/shared`
(Pydantic schemas) · `migrations/` (plain SQL → Neon Postgres + Timescale
+ pgvector, 001–006 applied).

Deeper docs: `architecture.md` (system + data flow + file map) → `Plan.md`
(phase roadmap §5 = current work) → `docs/improvement-plan-2026-06-11.md`
(audit P0–P3 + step plan) → `personalities.md` (persona specs, team-owned).

## State as of 2026-06-12 (read this first)

**Live in prod**: Phases A+B done. Daily 14-step ingest (Vercel cron 21:30
UTC weekdays → Cloud Run), weekly v2 persona batch (Fri 22:00 UTC: research
per ticker → ONE construction call → one analyst_reports row per persona),
live SSE chat, real reports/proposals in the UI. Phase C core shipped:
**risk gateway** (#94) validates every book pre-persist; **PaperEngine v1**
(#95) + `FEATURE_PAPER_EXECUTION=true` (#96) fills books at next bar open,
marks to market at close, writes `persona_performance`.

**Pending verification**: the paper engine's FIRST run (2026-06-12 21:30
UTC cron). Check: `persona_trades` / `persona_portfolios` /
`persona_performance` were 0 rows before it; expect 4 × $100K bootstraps +
first fills. If still 0, check `gcloud logging read ... textPayload:paper_engine`.

**PR trail (all squash-merged to main)**: #90 audit Step 0 hotfixes →
#93 re-land of Steps 1+2 (#91/#92 were merged into stack bases by mistake)
→ #94 risk gateway → #95 paper engine → #96 flag flip.

**Next up (improvement plan Step 3 remainder)**:
1. **← next dev slice** — Frontend performance/portfolio swap:
   `/api/performance` + `/api/portfolio` routes over
   `persona_performance`/`persona_portfolios`, then delete
   `lib/mock/performance.ts` (landing page still shows seeded random
   walks until the paper track has enough days to chart).
2. Gateway VaR/drawdown checks + Ray regime gate (positions now exist).
3. Operator console (~20 min): Grafana Cloud + Voyage key. Runbook:
   `docs/runbooks/observability-grafana-voyage.md`; dashboard JSON:
   `docs/grafana/llm-cost-dashboard.json`.
4. Optional 1y back-history for the performance chart — two options
   discussed 2026-06-12: frozen-book backfill ($0, must be labelled
   "hypothetical", look-ahead bias) vs point-in-time backtest replay
   (honest, ~$30–70 LLM). Decide when the frontend swap lands.

(mypy backlog: DONE 2026-06-12 — CI blocking with a pyproject
ignore_errors ledger for 16 legacy modules; see Commands section.)

## Commands

```powershell
# Worker (venv exists at apps/worker/.venv — never recreate)
cd apps\worker
.\.venv\Scripts\python.exe -m pytest tests -q                          # ~200 tests, no DB needed
.\.venv\Scripts\python.exe -m ruff check tessera_worker tests scripts  # MUST stay 0
.\.venv\Scripts\python.exe -m tessera_worker.jobs.ingest_daily --only features coverage

# Web
cd apps\web
npm run typecheck   # tsc --noEmit
npm run lint

# Deploy worker (operator): apps\worker\scripts\deploy_cloud_run.ps1
# DB: psql NOT installed locally — use Neon console SQL editor, or
# read-only queries via the worker venv (sqlalchemy + session_scope).
```

CI (`.github/workflows/ci.yml`): ruff + pytest + **mypy ALL BLOCKING**
(since 2026-06-12 — legacy modules sit in pyproject's
`[[tool.mypy.overrides]]` ignore_errors ledger; NEW modules must be
strict-clean and must NOT be added to the ledger), web tsc + lint.
gitleaks pre-commit configured. Repo is PUBLIC — never commit keys.

## Hard invariants (each one was a real incident — see improvement plan)

- **`ohlcv_1d` = one row per (ticker, calendar day).** Mixed sources once
  stored the same day twice (Alpaca 04:00Z vs Yahoo backfill 00:00Z),
  silently halving every row-window feature horizon for ~6 years (P0-1).
  Any new read path must `DISTINCT ON (ticker, ts::date)` (priority
  alpaca/coinbase > yahoo); any backfill must skip covered days. Tripwire:
  nightly SPY canary step, >100bps vs Yahoo fails the run (baseline 2.62).
- **Numbers in Python, narrative in LLM.** `features/compute.py` is the
  only path numbers reach prompts; the LLM never computes price/weight/P&L.
- **v2 batch = ONE analyst_reports row per persona per batch** (whole book
  in `parsed.proposals`; Pydantic + `normalize_book` force weights+cash=1.0).
  Book readers (API, paper engine) scope to `MAX(as_of_date)` ONLY —
  unioning across batch days resurrects dropped tickers (P0-2).
- **Every book passes `risk/gateway.py` before persisting** (universe
  membership, sum=1.0, single-name + sector caps). Rejection reasons feed
  the construction LLM's retry. Don't bypass it.
- **Paper engine NAV conservation is exact** (no fees in v1) and
  unit-pinned; book execution is idempotent via `report_id` on
  `persona_trades`. Fills at next bar OPEN, MTM at CLOSE, $100K bootstrap.
- **yfinance**: core dependency but always tier-3 fallback
  (FMP → SEC XBRL → yfinance), sanity-enveloped; its ingest steps fail
  loudly if missing — don't soften.
- **Budgets**: all Anthropic calls log to `llm_call_log`;
  `LLM_MAX_DAILY_COST_USD=5` global + `LLM_MAX_DAILY_COST_CHAT_USD=2`
  chat-only pool (public chat must not starve the Friday batch).
- **Chat endpoint is public until Phase D** — keep guards: message ≤4K,
  history sanitized ≤20 turns, Edge per-IP rate limit (10/min).
- `ingest_daily` holds a Postgres advisory lock — duplicate triggers no-op.

## Ops facts

- `WORKER_WEBHOOK_URL` (Vercel) = **base** Cloud Run URL, no `/jobs/...`
  path. Both URL styles Cloud Run prints are the same service.
- Cloud Run runs `--no-cpu-throttling` (BackgroundTasks survive past the
  202). Structural fix = Cloud Run Jobs, still open.
- Feature flags (deploy script env line): `FEATURE_REAL_LLM=true`,
  `FEATURE_PAPER_EXECUTION=true`, `FEATURE_LIVE_TRADING=false` (never
  flip without compliance). Quick flag change without rebuild:
  `gcloud run services update tessera-worker --region us-east1 --update-env-vars K=V`.
- After any ohlcv-touching migration: rebuild features
  (`--only features coverage`) + run the SPY canary.
- Daily cron 21:30 UTC weekdays; weekly batch Fri 22:00 UTC; Friday's book
  fills at Monday's open by design.

## Process gotchas (Windows / GitHub)

- **Stacked PRs: merge bottom-up and DELETE each base branch** (or rely on
  auto-delete). #91/#92 once merged into their stack bases instead of main
  and had to be cherry-pick re-landed (#93). Verify with
  `gh pr view N --json baseRefName,state` when in doubt.
- PowerShell here-strings break with `git commit -m` / `gh pr create
  --body` — always write to a temp file and use `-F` / `--body-file`.
- Repo text contains UTF-8 em-dashes/box-chars that PowerShell `Get-Content`
  mangles (cp1252) — use the Read tool for exact Edit match strings.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`;
  main is branch-protected — every change goes through a squash-merge PR.
- The user (정우) operates gcloud/Neon-console/Vercel steps themselves —
  hand them exact commands; don't run prod-mutating commands without asking.

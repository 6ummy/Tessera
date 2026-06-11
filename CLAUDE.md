# CLAUDE.md — working notes for Claude Code sessions

Tessera: 4 AI analyst personas (Warren/Cathie/Ray/Peter) write weekly LLM
theses over a shared data plane; paper-trading pilot. Monorepo:
`apps/web` (Next.js 14, Vercel) · `apps/worker` (Python 3.11 FastAPI,
Cloud Run) · `packages/shared` (Pydantic schemas) · `migrations/` (plain
SQL, Neon Postgres + Timescale + pgvector).

Read in this order when context is missing: `README.md` →
`architecture.md` (system + data flow, file map) → `Plan.md` (phase
roadmap, what's done/queued) → `docs/improvement-plan-2026-06-11.md`
(audit findings P0–P3 + step plan) → `personalities.md` (persona specs —
team-owned, big voice changes need a heads-up).

## Commands

```powershell
# Worker (venv already exists at apps/worker/.venv)
cd apps\worker
.\.venv\Scripts\python.exe -m pytest tests -q        # all tests, no DB needed
.\.venv\Scripts\python.exe -m ruff check tessera_worker tests scripts  # MUST stay 0
.\.venv\Scripts\python.exe -m tessera_worker.jobs.ingest_daily --only features coverage

# Web
cd apps\web
npm run typecheck    # tsc --noEmit
npm run lint

# Deploy worker (operator): apps\worker\scripts\deploy_cloud_run.ps1
# Migrations: psql is NOT installed locally — use Neon console SQL editor,
# or run SQL via the worker venv (psycopg) against DATABASE_URL.
```

CI (`.github/workflows/ci.yml`): ruff + pytest blocking; `mypy --strict`
non-blocking (216-error backlog — don't add to it). gitleaks pre-commit
configured; repo is PUBLIC (ADR-007), never commit keys.

## Hard invariants (violations have bitten us — see improvement plan)

- **`ohlcv_1d` = one row per (ticker, calendar day).** PK is `(ticker, ts
  TIMESTAMPTZ)` and mixed sources once stored the same day twice (Alpaca
  04:00Z vs Yahoo 00:00Z), silently halving every row-window feature
  horizon for ~6 years of data (P0-1). Migration 006 cleaned it; any new
  read path must dedup `DISTINCT ON (ticker, ts::date)` (source priority:
  alpaca/coinbase > yahoo) and any backfill must skip already-covered days.
- **Numbers in Python, narrative in LLM.** The LLM never computes a
  price/weight/return; `features/compute.py` is the only path numbers
  reach prompts.
- **v2 persona batch = ONE `analyst_reports` row per persona per batch**
  (whole book in `parsed.proposals`, Pydantic enforces weights+cash=1.0).
  Book readers must scope to `MAX(as_of_date)` only — unioning rows
  across batch days resurrects dropped tickers (P0-2 "ghost positions").
- **yfinance is a core worker dependency** (since 2026-06-11) but always
  tier-3 fallback (FMP → SEC XBRL → yfinance), sanity-enveloped. The yf
  ingest steps fail loudly if it's missing — don't soften that.
- **Budgets**: every Anthropic call logs to `llm_call_log`;
  `LLM_MAX_DAILY_COST_USD` (global, $5 prod) + `LLM_MAX_DAILY_COST_CHAT_USD`
  ($2, chat-only pool so public chat can't starve the Friday batch).
- **Chat endpoint is public until Phase D** — keep the guards: message ≤4K
  chars, history sanitized ≤20 turns, Edge per-IP rate limit.
- `ingest_daily` holds a Postgres advisory lock (duplicate trigger no-ops)
  and ends with the SPY canary step (>100bps vs Yahoo fails the run —
  this is the tripwire for P0-1-class regressions; live baseline 2.62bps).

## Ops facts

- `WORKER_WEBHOOK_URL` (Vercel) = **base** Cloud Run URL, no `/jobs/...`
  path (gcp-auth.ts strips paths; IAM token audience must be the bare URL).
  Both URL styles Cloud Run prints point at the same service.
- Cloud Run service runs with `--no-cpu-throttling` (BackgroundTasks
  survive after the 202). Structural fix = Cloud Run Jobs, still open.
- Crons: daily ingest `30 21 * * 1-5`, weekly persona batch `0 22 * * 5`
  (both Vercel cron → worker; see `apps/web/vercel.json`).
- After applying an ohlcv-touching migration: rebuild features
  (`--only features coverage`) + run SPY canary.

## Process gotchas (Windows / GitHub)

- **Stacked PRs: merge bottom-up and DELETE each base branch** (or keep
  "Automatically delete head branches" on). #91/#92 were once merged into
  their stack bases instead of main and had to be re-landed (#93).
- PowerShell here-strings passed to `git commit -m` / `gh pr create --body`
  break unpredictably — write the text to a temp file and use
  `git commit -F <file>` / `gh pr create --body-file <file>`.
- The Edit tool's exact-match strings: this repo has UTF-8 em-dashes and
  box-drawing chars; PowerShell `Get-Content` mangles them (cp1252), so
  Read tool output is the source of truth for match strings.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`;
  squash-merge via PR only (branch protection on main).

## Current state (2026-06-11) + what's next

Phase B done; Phase C (paper execution) in progress. Audit Steps 0–2
merged (#90, #93); risk gateway shipped 2026-06-11 (`risk/gateway.py`,
wired into `construct_portfolio`'s retry loop — universe membership,
sum=1.0, single-name + sector caps; VaR/drawdown wait for the paper
engine). Next per improvement plan Step 3:
1. **PaperEngine** + order ledger + EOD mark-to-market →
   `persona_performance` (this also unblocks VaR/drawdown in the gateway).
2. Frontend mock swap (`lib/mock/performance.ts` still shows seeded random
   walks on the landing page — intentional until real P&L exists).
3. mypy backlog burn-down (then flip CI mypy to blocking).

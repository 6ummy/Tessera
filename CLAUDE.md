# CLAUDE.md — operator handbook for AI sessions (zero-context handoff)

You are working on **Tessera** with 정우 (@6ummy, Korean, replies in
Korean — answer in Korean, keep code/identifiers/commits in English).
Read this file top to bottom once; it is written so you can act without
any prior conversation.

## 1. What this product is

4 AI analyst personas — Warren (value), Cathie (disruptive growth +
crypto), Ray (macro regime allocator, ETF book), Peter (GARP) — write
weekly Sonnet 4.6 investment theses over a shared market-data plane.
A deterministic paper engine executes each persona's book against a
$100K virtual account; the Next.js site shows their books, P&L, and a
live chat with each persona. **Paper trading only. `FEATURE_LIVE_TRADING`
stays false until Phase E/F legal clearance — never flip it.**

Monorepo: `apps/web` (Next.js 14 App Router, Vercel) · `apps/worker`
(Python 3.11 FastAPI on Cloud Run `tessera-worker`, us-east1, project
`tessera-498200`) · `packages/shared` (Pydantic schemas) ·
`migrations/` (plain SQL → Neon Postgres + Timescale + pgvector,
**001–007 all applied to prod**).

## 2. State as of 2026-06-13

Everything below is LIVE in prod unless marked otherwise:

- **Daily 14-step ingest**, weekdays 21:30 UTC: Vercel cron →
  `/api/cron/daily` → Cloud Run `/jobs/ingest-daily` → ohlcv (Alpaca +
  Coinbase) → FRED → fundamentals 3-tier (FMP → SEC XBRL → FMP
  key-metrics → yfinance shares daily / history Fri) → news → SEC
  filings → features → coverage audit → **SPY canary** (>100bps vs
  Yahoo fails the run; baseline 2.62bps) → **paper engine**
  (`FEATURE_PAPER_EXECUTION=true`). Advisory-locked (dup trigger no-ops).
- **Weekly persona batch**, Fri 22:00 UTC: v2 two-pass — research call
  per shortlist ticker, then ONE construction call per persona →
  `normalize_book` (deterministic sum=1.0) → **risk gateway** →
  ONE `analyst_reports` row per persona. Hallucination canary chains after.
- **Paper track**: engine bootstrapped 4 × $100K on 2026-06-11 (36
  fills); plus a **251-day hypothetical backfill** per persona
  (frozen-book: current holdings projected back 1y, `hypothetical=true`
  flag in DB/API, look-ahead bias). 1y hypothetical: ray +16.0%,
  peter +8.4%, cathie −2.0%, warren −7.0%. **UI policy (product decision
  2026-06-12): one solid line per persona, no dashed split — captions
  state "real fills since Jun 11, 2026"; the hypothetical flag stays in
  the data and `/api/performance` for any future use.**
- **Frontend**: all real — reports/proposals/chat (since 06-05),
  performance/portfolio (since 06-12, mock deleted). Remaining mocks:
  dashboard "My portfolio" positions + Social tab (Phase-D demos,
  labelled) and auth (assumes "jshin").
- **Observability**: Grafana Cloud dashboard over `llm_call_log`
  (`docs/grafana/llm-cost-dashboard.json`); Sentry errors-only; Voyage
  embeddings on prod (similarity recall fires in the WEEKLY BATCH logs
  as `sim=0.xx` — chat has no memory recall, that's Phase D).
- **CI** (`.github/workflows/ci.yml`): ruff + pytest + mypy ALL
  blocking (mypy via a legacy `ignore_errors` ledger in
  `apps/worker/pyproject.toml` — NEW modules must be strict-clean and
  must NOT be added to the ledger). gitleaks pre-commit configured.
- **Risk/analytics layer (#105–#108, deployed 06-12 PM)**: gateway now
  full — VaR99 (`risk/var.py`, per-persona caps calibrated vs measured
  books) + drawdown floor (live track only) + Ray's `gate_regime`;
  weight-distribution telemetry (canary check 6, §11 tripwire);
  ticker-level attribution (`/api/attribution`, contributions sum to
  period return); paper-engine failures page via explicit Sentry
  capture + operator alert rule. Known: warren/cathie's pre-#94 books
  violate SECTOR caps → the next Friday batch re-shapes them via retry
  feedback (expected `risk_gateway.rejected` → `passed` log pairs).
- **PR trail this week**: #90 audit hotfixes → #93 re-land Steps 1+2 →
  #94 risk gateway → #95/#96 paper engine + flag → #98 Ray as_of fix →
  #99 mypy/tests/observability → #100 backfill → #103 frontend swap →
  #105 VaR/DD/Ray gate → #106 weight telemetry → #107 attribution →
  #108 Sentry paging → #110 parse-leading-prose → #111 recall sim= fix
  → #112 case-studies → #114 cathie sector cap 0.70 → #116 Cloud Run
  Jobs → #117 attribution UI → #118 main.py mypy burn. (Doc syncs
  along the way: #97/#101/#102/#104/#109/#113/#115.)

## 3. Hard invariants (each from a real incident — don't relearn them)

- **`ohlcv_1d` = ONE row per (ticker, calendar day).** Mixed sources
  once stored the same day twice (Alpaca 04:00Z vs Yahoo 00:00Z) and
  silently halved every row-window feature horizon for ~6y (P0-1, #90).
  New read paths: `DISTINCT ON (ticker, ts::date)` with source priority
  alpaca/coinbase > yahoo. Backfills must skip covered days. The
  nightly SPY canary is the tripwire.
- **Numbers in Python, narrative in LLM.** `features/compute.py` is the
  only path numbers reach prompts. The LLM never computes a price,
  weight, or P&L. Sizing intent from the LLM is normalized
  deterministically (`normalize_book`).
- **Book readers scope to `MAX(as_of_date)` only.** v2 writes one row
  per persona per batch; unioning across batch days resurrects dropped
  tickers ("ghost positions", P0-2).
- **Server-authoritative fields are force-set, never `setdefault`.**
  Ray's LLM volunteered its own `as_of` and won the tie for weeks (#98).
- **Every book passes `risk/gateway.py` pre-persist** — stock-pickers
  via `gate()`, Ray via `gate_regime()`: universe membership, sum=1.0,
  single-name + sector caps, parametric VaR99 vs calibrated persona
  caps (3.5/8.5/4.5/2.5%), drawdown floor on the LIVE track
  (20/35/25/15%). Rejection reasons feed the construction retry.
  "VaR unmeasurable" (<60 aligned obs) is soft — never rejects.
  **Why hard-gate even when the prompt already states the caps**:
  CS-11 documents Cathie repeatedly busting the sector cap after
  explicit error feedback — LLM role-immersion can outweigh stated
  rules, so the system-level stop is non-negotiable.
- **Paper engine**: NAV conservation exact (no fees v1), execution
  idempotent via `report_id` on `persona_trades`, fills at next bar
  OPEN, MTM at CLOSE. Hypothetical rows are write-guarded
  (`WHERE hypothetical`) — real rows are untouchable by the backfill.
- **Budgets**: every Anthropic call logs to `llm_call_log`. Global
  $5/day + chat-only $2/day pool (public chat must not starve Friday's
  batch). `check_daily_budget()` hard-pauses.
- **Chat is public until Phase D** — keep the guards: message ≤4K,
  history sanitized ≤20 turns, Edge 10/min/IP rate limit.
- **yfinance**: core dependency, but strictly tier-3 fallback,
  sanity-enveloped; its steps fail loudly if missing.
- **Sanity bound ≠ freshness check.** ±100% / margin envelopes / P/E
  caps catch unit + currency errors, NOT "upstream provider's mapping
  silently dropped → loader walked back to a 2.7-yr stale row that
  happens to be in-band" (CS-13, COIN). Every value that comes out of
  a loader walk-back must carry its newest-period_end meta forward;
  downstream guards drop values whose freshness exceeds a clear bound
  (FCF: `FCF_STALENESS_MAX_DAYS=400` ≈ 13 months).
- **No silent failures — this codebase's #1 bug class** (see CS-3,
  CS-4, CS-5, CS-6, CS-12, CS-13 in `docs/case-studies.md` for the
  canonical cases). Every caught exception logs loudly with context
  or re-raises;
  `suppress` / `except: pass` / `setdefault` on LLM-overlapping fields
  need written justification. A step where every item "skipped" is a
  FAILURE, not a success. **Don't pass the full universe to a
  source-specific ingest** — equity steps send `by_asset_class("equity")
  +("etf")` only; Alpaca rejects a crypto symbol and fails the whole
  batch (CS-12, hidden for 9 days because the Service ignored exit
  codes). When you fix a nontrivial bug, ADD A CS ENTRY to
  case-studies.md (presentation material) in the same PR.

## 4. Commands (Windows / PowerShell)

```powershell
# Worker — venv EXISTS at apps/worker/.venv, never recreate it
cd apps\worker
.\.venv\Scripts\python.exe -m pytest tests -q                          # 242 tests, no DB needed
.\.venv\Scripts\python.exe -m ruff check tessera_worker tests scripts  # MUST stay 0
.\.venv\Scripts\python.exe -m mypy tessera_worker                      # MUST stay 0
.\.venv\Scripts\python.exe -m tessera_worker.jobs.ingest_daily --only features coverage

# Web
cd apps\web
npm run typecheck    # tsc --noEmit
npm run lint

# Deploy worker (rebuild + ship; operator runs it, or hand them the cmd)
.\apps\worker\scripts\deploy_cloud_run.ps1
# Flag-only change without rebuild:
#   gcloud run services update tessera-worker --region us-east1 --update-env-vars K=V
```

**DB access**: psql is NOT installed locally. Read-only queries → write
a small script using `tessera_worker.db.session_scope` and run it with
the venv python (this is routine and allowed). Schema changes / row
deletes → migrations applied by the operator in the Neon console SQL
editor. Never run prod-mutating jobs without explicit user consent in
the conversation.

## 5. Architecture in one breath

Vercel cron → Cloud Run FastAPI (`tessera_worker/main.py`) →
`jobs/ingest_daily.py` STEPS dict (idempotent, advisory-locked) →
Neon. Weekly: `jobs/persona_batch.py run_batch_v2` →
`agents/portfolio_construction.py` (+ `risk/gateway.py`) →
`analyst_reports`. Nightly: `risk/paper_engine.py` (fill/MTM/perf) →
`persona_trades` / `persona_portfolios` / `persona_performance`.
UI reads via worker HTTP endpoints proxied by Next Edge routes
(`apps/web/app/api/*` → IAM identity token via `lib/gcp-auth.ts`).

Key worker endpoints: `/api/reports/{p}`, `/api/proposals/{p}` (latest
batch day only), `/api/performance/{p}` (curve + hypothetical flags),
`/api/portfolio/{p}` (real snapshot only), `/api/attribution/{p}`
(?period=mtd|7d|30d), `/api/features/{t}`, `/api/prices/{t}`,
`/api/chat/{p}` (SSE), `/jobs/ingest-daily`, `/jobs/persona-batch`.

Key tables: `ohlcv_1d`, `ticker_features` (the only numbers LLMs see),
`fundamentals` (JSONB, 3-tier merged), `analyst_reports` (parsed book
JSONB; `rejected` flag), `persona_trades/portfolios/performance`
(+ `hypothetical` flag), `llm_call_log`, `persona_memory` (pgvector).

## 6. Process rules (violations have burned us)

- main is branch-protected: every change = branch → squash-merge PR.
  Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Stacked PRs: merge bottom-up AND delete each base branch** — GitHub
  only retargets children when the base is deleted; #91/#92 once merged
  into their bases instead of main and needed a cherry-pick re-land (#93).
  When unsure: `gh pr view N --json baseRefName,state`.
- PowerShell here-strings break `git commit -m` / `gh pr create --body`
  → always write to a temp file, use `-F` / `--body-file`.
- Repo text has UTF-8 em-dashes/box-chars; PowerShell `Get-Content`
  reads them as cp1252 mojibake. **Use the Read tool for Edit match
  strings; never bulk-rewrite files via PowerShell `-replace`** (it
  corrupted paper_engine.py once; had to restore from git).
- **`curl` in PowerShell is an alias for `Invoke-WebRequest`, NOT real
  curl.** `-H "Authorization: Bearer X"` fails with `Cannot bind
  parameter 'Headers'. Cannot convert ... String to ... IDictionary`.
  Either: (a) call real curl as `curl.exe -H "..."`, or (b) use the
  native form `Invoke-WebRequest -Uri ... -Headers @{ "Authorization"
  = "Bearer $TOKEN" }`. Same trap appears for any `-H` / `--header` /
  `-d` flag you copy-pasted from a Linux/Mac snippet.
- **Cloud Run worker is `--no-allow-unauthenticated`** — only
  `serviceAccount:tessera-vercel@...` is bound to `roles/run.invoker`.
  Direct `curl https://tessera-worker-...` from a dev box returns
  `Error: Forbidden / Your client does not have permission` at
  Google's edge (the request never reaches the app). For ad-hoc
  testing add your own user once with
  `gcloud run services add-iam-policy-binding tessera-worker --region
  us-east1 --member="user:<email>" --role="roles/run.invoker"`, then
  pass an ID token via `gcloud auth print-identity-token`. Health
  checks are rarely needed anyway — a `gcloud run services describe`
  showing the latest revision as `Ready` is a stronger signal than
  `/health` 200 (readiness probe already gated it).
- The operator (정우) runs gcloud/Neon/Vercel console steps — hand exact
  commands. Verify their reports with read-only queries when cheap.
- After any ohlcv-touching migration: rebuild features
  (`--only features coverage`) + run SPY canary.
- Docs are part of done: update Plan.md (+ its versioning table),
  architecture.md, improvement plan, and this file in the same PR as
  the change they describe.

## 7. Debugging entry points

- Cron ran? `gcloud logging read "resource.labels.service_name=tessera-worker" --freshness=1d`
  (filter `textPayload:paper_engine`, `:sim=`, `:step_failed` as needed).
- Data fresh? `SELECT MAX(fetched_at) FROM news;` / latest `ts` per table.
- Ticker blank in UI? `python -m scripts.inspect_ticker_features <T>`
  walks the whole fundamentals fall-through.
- Book looks wrong? Check `analyst_reports` latest `as_of_date` row's
  `parsed`, then `risk_gateway.*` log lines, then `paper_engine.*`.
- Cost spike? Grafana dashboard or `SELECT stage, SUM(cost_usd) FROM
  llm_call_log WHERE ts >= CURRENT_DATE GROUP BY 1;`

## 8. Backlog (priority order, with pointers)

1. **90-day point-in-time backtest baseline** — credibility anchor;
   harness exists (`jobs/backtest_harness.py`), ~$10–20 LLM. Plan §5 Week 5.
2. **mypy ledger burn-down** — 12 modules left after the 2026-06-14
   burn of `features/compute.py` (~26), `agents/anthropic_runner.py` (~19),
   `agents/prompt_assembler.py` (~14). Remaining: 4 demo modules,
   `agents.portfolio_construction`, `agents.ticker_resolver`,
   `agents.chat`, the ingestors.* glob, and the 4 jobs (hallucination_canary,
   persona_batch, backtest_harness, backfill_history).
3. **hit_rate** (needs closed-lot tracking) · quarterly margin series
   ingest (low) · §10 weight-authority decision once a few weeks of
   `canary.weight_telemetry` accumulate · Phase D (auth, follow, chat
   memory) per Plan §6.

Done 2026-06-12/13: Gateway VaR/DD/Ray + attribution endpoint + weight
telemetry (#105–#108); **Cloud Run Jobs migration** (#116,
`deploy_cloud_run_jobs.ps1` + `docs/runbooks/cloud-run-jobs.md` — batches
run to completion, no more BackgroundTask reaping; the cutover
[Cloud Scheduler on, Vercel crons off] is an operator console step; the
first test-run also surfaced CS-12, fixed in #119);
**attribution UI table** in the detail sheet (#117); **main.py mypy
burn-down** (#118); **equity-ingest crypto-exclusion** (#119, CS-12 —
equity OHLCV had silently frozen 9 days because Alpaca rejected a
crypto symbol and the Service ignored the exit code).

## 9. Doc map

`README.md` (quick start) → `architecture.md` (system + data flow +
file map; §6 is current-state) → `Plan.md` (phase roadmap; §5 = Phase C
live state; versioning table at bottom) →
`docs/improvement-plan-2026-06-11.md` (the audit that drove this week;
P0–P3 + step statuses) → per-phase "Lessons" live INSIDE Plan.md
(§3 Phase A, §4 Phase B, §5 Phase C running list — keep that
convention, no separate retro files) → **`docs/case-studies.md`**
(presentation-ready bug write-ups CS-1…CS-10; append on every
nontrivial fix) → `docs/runbooks/` (observability, Cloud Run IAM)
→ `personalities.md`
(persona specs — TEAM-OWNED, big voice changes need a 카톡 heads-up).
CONTRIBUTING.md has the team/track map (5 people; you mostly interact
with 정우).

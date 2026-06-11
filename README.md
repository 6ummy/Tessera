# Tessera

> A multi-agent LLM research desk for long-term investing. Four AI analyst
> personas — each with a distinct philosophy and voice — publish daily theses
> and portfolios side-by-side. Paper-trading pilot today, live-execution ready
> by design.

```
🌐 Repo:           github.com/6ummy/Tessera
📐 Architecture:   architecture.md
🗺️ Build plan:     Plan.md       (6-week phased pilot)
🧑‍💼 Personas:       personalities.md  (LLM-ready system prompts + chat fine-tuning specs)
🪩 Deck:           tessera-deck.pptx (17 slides, technical)
🩺 Audit:          docs/improvement-plan-2026-06-11.md (findings + step-by-step plan)
```

## Monorepo layout

```
apps/
  web/                Next.js 14 frontend (Vercel)
  worker/             Python batch worker — ingestors, features, agents, risk, paper engine
packages/
  shared/             Pydantic schemas shared across worker boundaries
migrations/           Plain SQL files for Neon Postgres (Timescale + pgvector)
docs/                 Phase retros, ADRs
build-deck.js         Generates tessera-deck.pptx
```

## Quick start

### Frontend (already shipped — works today)

```bash
cd apps/web
npm install
npm run dev
# → http://localhost:3000
```

### Worker (local dev)

```bash
cd apps/worker
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash; Mac/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env             # then fill keys (DB + 6 API keys + SENTRY_DSN)
python -m tessera_worker.main    # → http://localhost:8080/health
```

To run one full ingest locally (writes to the shared Neon DB):

```bash
python -m tessera_worker.jobs.ingest_daily
# 14 steps (ingest → features → coverage audit → SPY canary → paper
# engine [flag-gated]), usually ~5-10 min in steady state. Use
# --only/--skip to run a subset.
# Guarded by a Postgres advisory lock — a second concurrent run no-ops.
```

To recompute only deterministic features from already-ingested Neon data:

```bash
python -m tessera_worker.jobs.ingest_daily --only features
# Rebuilds price/momentum history and latest fundamentals-derived features
# such as fcf_yield, peg, eps_cagr_3y, debt_to_equity, and gross_margin.
```

### Database

Provisioned and shared across the team. Get `DATABASE_URL` from the team
KakaoTalk credential pin. The shared schema is already applied; to bootstrap
a fresh Neon project (or your own dev branch), apply migrations in numeric
order:

```bash
psql "$DATABASE_URL" -f migrations/001_init.sql
psql "$DATABASE_URL" -f migrations/002_persona_memory_vector_1024.sql
psql "$DATABASE_URL" -f migrations/003_backtest_reports.sql
psql "$DATABASE_URL" -f migrations/004_quality_features.sql
psql "$DATABASE_URL" -f migrations/005_pe_ratios.sql
psql "$DATABASE_URL" -f migrations/006_ohlcv_canonical_day.sql
```

### Production runtime (cloud)

```
Vercel Cron (21:30 UTC weekdays)
   → /api/cron/daily        (Bearer CRON_SECRET)
   → Cloud Run worker       (us-east1, tessera-worker)
   → /jobs/ingest-daily     (IAM identity token / Bearer fallback)
   → 14-step ingest         (BackgroundTask, ~5-10 min steady state)
   → Neon Postgres          (single source of truth)
```

- Worker image build + deploy: `apps/worker/scripts/deploy_cloud_run.ps1`
  (`WORKER_WEBHOOK_URL` in Vercel is the BASE service URL, no `/jobs/...` path)
- Secrets live in GCP Secret Manager (mounted as env in Cloud Run)
- Observability: GCP Logging (structured JSON) + Sentry (errors only, both
  `tessera-web` and `tessera-worker` projects)

See `architecture.md` §6 "Daily data flow" for the full diagram.

## Phase status

| Phase | Status | What it ships |
|---|---|---|
| **Frontend MVP** | ✅ shipped | 4 routes, 4 personas with photos + bios + chat UI, all on Vercel |
| **A — Data backbone** (wk 1) | ✅ shipped | Ingestors + features + Neon schema + Cloud Run worker + Sentry |
| **B — Real LLM theses** (wks 2–3) | ✅ shipped | Weekly persona batch, live reports/proposals, SSE chat, pgvector recall |
| **C — Paper execution** (wks 4–5) | 🚧 in progress | Risk gateway + paper engine + real P&L; quality features pre-shipped; **data resilience layer** (3-tier fundamentals fall-through FMP → EDGAR XBRL → yfinance + per-field newest-non-null walk) shipped 2026-06-09 |
| **D — User auth + follow** (wk 6) | ⏳ planned | Firebase Auth + 3 F&F users |
| **E — Compliance** (wk 6, parallel) | ⏳ planned | Securities-lawyer consult |
| **F — Live trading** (wk 7+, optional) | ⏳ planned | Alpaca OAuth, behind feature flag |

See `Plan.md` for week-by-week task breakdown, acceptance criteria, risk
register, and open decisions. See `docs/adr/` for the "why" behind major
technical choices.

## Why "Tessera"

A `tessera` is a small tile in a mosaic. Each analyst is one tile —
distinct philosophy, distinct voice, distinct trade-offs — and together
they form a complete picture of how a thoughtful investor might read
today's market.

## License + disclaimers

Internal pilot. Not investment advice. Tessera does not custody funds, place
live orders without explicit user approval, or provide personalized
recommendations. See the "Where you stand" section of `/how-it-works` in the
web app.

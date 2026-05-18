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
🎤 Talk script:    deck-script-ko.md
🪩 Deck:           tessera-deck.pptx (17 slides, technical)
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

### Worker (Phase A in progress)

```bash
cd apps/worker
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash; Mac/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env             # then fill keys
python -m tessera_worker.main    # → http://localhost:8080/health
```

### Database

```bash
# After provisioning Neon (free tier): apply the v1 schema
psql "$DATABASE_URL" -f migrations/001_init.sql
```

## Phase status

| Phase | Status | What it ships |
|---|---|---|
| **Frontend MVP** | ✅ shipped | 4 routes, 4 personas with photos + bios + chat UI, all on Vercel |
| **A — Data backbone** (wk 1) | 🚧 in progress | Ingestors + features + Neon schema |
| **B — Real LLM theses** (wks 2–3) | ⏳ planned | Anthropic SDK + Pydantic validation |
| **C — Paper execution** (wks 4–5) | ⏳ planned | Risk gateway + paper engine + real P&L |
| **D — User auth + follow** (wk 6) | ⏳ planned | Firebase Auth + 3 F&F users |
| **E — Compliance** (wk 6, parallel) | ⏳ planned | Securities-lawyer consult |
| **F — Live trading** (wk 7+, optional) | ⏳ planned | Alpaca OAuth, behind feature flag |

See `Plan.md` for week-by-week task breakdown, acceptance criteria, risk
register, and open decisions.

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

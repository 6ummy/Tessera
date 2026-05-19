<!--
  PR title format:  <track>: <short imperative>
  e.g. "llm: add Warren persona runner with prompt caching"
       "frontend: fix mobile nav overflow on /dashboard"
       "quant: add FCF yield + PEG features from FMP fundamentals"
-->

## What

<!-- 1–3 sentences: what does this PR change? -->

## Why

<!-- The motivation: which Plan.md task, issue, or insight prompted this. -->

## How

<!-- Approach + any noteworthy design decisions. Link ADR if applicable. -->

## Track

- [ ] Frontend (한솔)
- [ ] LLM Pipeline (윤채/한솔)
- [ ] Quant (예슬)
- [ ] Infra (윤채)
- [ ] Docs / Persona voice (정우)
- [ ] Cross-track  → list which: _____

## Acceptance — track-specific (delete sections that don't apply)

### Frontend
- [ ] `npm run build` clean
- [ ] `npm run lint` clean
- [ ] Mobile (≥375 px) renders without overflow
- [ ] Loading + error states present for any new data fetch
- [ ] Colors come from tailwind config tokens, not raw hex

### LLM Pipeline
- [ ] Pydantic schema defined + validation tested
- [ ] Citation check passes (`cited_news_ids` resolve in `news` table)
- [ ] 1+ fixture/property test added
- [ ] LLM call logs `cost_usd` + `tokens_in/out` to `llm_call_log`
- [ ] Voice eval set re-run if persona prompt touched

### Quant
- [ ] `pytest tests/` 13+/13+ green
- [ ] Property test added for any new feature
- [ ] Canary assert (≤ 10 bps to external source) for return-related features
- [ ] Schema migration added if new column needed (NULL-allowed)

### Infra
- [ ] Dockerfile builds locally
- [ ] No secrets committed; all via Secret Manager / Vercel env
- [ ] New loggers silence sensitive URL/header patterns (`logging.py`)
- [ ] Cost impact estimated in description (if positive)

## Common safety checks (all PRs)

- [ ] No `console.log` / `print()` of API keys, tokens, or PII
- [ ] `.env`, `.env.local`, secrets never staged
- [ ] New env var → added to `.env.example`
- [ ] New dep → version pinned in `pyproject.toml` / `package.json`
- [ ] Branch is up to date with `main` (rebased)

## Cost estimate (if LLM-related)

<!--
  Required for PRs that add or change Anthropic calls.
  Example:
    "Adds chat backend SSE streaming. Sonnet 4.6 ~$0.012/msg with caching.
     Expected +$2–5/day at current chat volume; alert threshold unchanged."
  If no cost change: just write "None — feature/test only".
-->

None / _____

## Migration (if schema touched)

- [ ] New file `migrations/NNN_*.sql` with next sequential N
- [ ] Idempotent (CREATE TABLE IF NOT EXISTS, etc.)
- [ ] Applied to staging Neon before requesting review

## Screenshots / output (if relevant)

<!-- Frontend: before/after. LLM: example output. Quant: chart or row sample. -->

## Linked issues / docs

Closes #___
Refs `Plan.md` § ___ , `architecture.md` § ___

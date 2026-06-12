# Retro — Phase B: Real LLM theses (2026-06-02 → 2026-06-05)

> The Plan §9 commitment: a short retro per phase. Phase B took the desk
> from "data plane with mock theses" to "four personas writing real
> Sonnet 4.6 research, live chat, real reports/proposals in the UI."
> Written 2026-06-12 (late — captured while Phase C was already landing,
> which itself is a lesson: write the retro the week the phase ends).

## What shipped

- **agents/ package end-to-end**: persona_loader (personalities.md →
  specs), prompt_assembler (6-part prompt, point-in-time `as_of` bounds
  on every query), anthropic_runner (typed calls, 2-attempt retry with
  targeted feedback, cost logging + daily budget hard-pause),
  citation_validator (every cited news id must resolve).
- **Ray's parallel schema**: RegimeReport (ETF allocations + regime
  probabilities) persisted into the same `analyst_reports` table via
  `persona_id='ray'` discriminator — one source of truth for "what did
  the desk say".
- **Weekly cadence decision**: Friday 22:00 UTC batch (~$1.35/run ≈
  $5–7/mo) over daily (~$72/mo). `persona_batch.py` + Vercel cron made
  `FEATURE_REAL_LLM=true` actually mean something.
- **Backtest harness** with leakage tests (every fetch upper-bounded on
  `as_of`), separate `backtest_reports` table, <2% schema-fail
  acceptance gate (measured 1.67%, then 0% after fixes).
- **Hallucination canary**: post-hoc invariants on persisted rows
  (citations resolve, no weight at the schema cap, conviction floors,
  compliance-phrase grep, persona-topic drift).
- **Live SSE chat** (Sonnet 4.6, 6-part system prompt, ticker-aware RAG)
  + frontend consumer; mock chat deleted.
- **Frontend thesis swap**: reports + proposals mocks deleted, Edge
  proxies + uniform `{positions, cashWeight, regime?}` reshaping.
- **pgvector recall**: Voyage embeddings, similarity-or-recency at
  runtime, persisted best-effort (never blocks).

## Acceptance criteria — all green 2026-06-05

| Criterion | Result |
|---|---|
| Real thesis in UI w/ resolving citations | ✅ |
| Chat in persona voice | ✅ (~$0.003/msg cached) |
| < $5/day cost | ✅ (weekly ≈ $1.35/run) |
| Backtest schema-fail < 2% | ✅ 1.67% (60-cell), 0% (18-cell follow) |
| 0 hallucinated tickers reaching UI | ✅ |

## What we learned (the expensive way)

1. **Silent signal loss is the worst failure mode.** A field rename in
   personalities.md (`confidence` → `conviction`) zeroed a signal with
   no error anywhere. Fix was a defensive alias + the lesson: every
   LLM-output field needs a consumer-side existence check or a canary.
2. **LLMs decorate JSON.** ~5% of Cathie's cells appended narrative
   after the closing brace. `JSONDecoder.raw_decode` (parse the first
   object, log the rest) beat prompt-nagging.
3. **Retry feedback must be specific.** Generic "fix your JSON" retries
   wasted attempts; pattern-matching the validation error and telling
   the model exactly what to change (`_retry_guidance_for`) made the
   second attempt actually converge.
4. **Single-source fundamentals fail per-ticker, not globally.** Visa
   broke FMP and XBRL differently than NVDA did. This insight became
   Phase C's 3-tier fall-through (FMP → SEC XBRL → yfinance) with
   per-field newest-non-null walking.
5. **Per-cell sizing can't produce a coherent book.** Warren's 8% BRK.B
   + nine 0% rows + "12% cash" summing to 20% exposed the structural
   flaw in one-LLM-call-per-ticker sizing → the v2 two-pass redesign
   (research per ticker, ONE construction call per persona,
   deterministic `normalize_book`).
6. **(Found later, P0-class)** Trusting any LLM-volunteered value over a
   server value is a bug waiting to happen: `setdefault("as_of", ...)`
   let Ray stamp 17-month-old dates on fresh reports for weeks (#98).
   Server-authoritative fields must be force-set.

## What we'd do differently

- Write the canary BEFORE the first prod batch, not after — items 1 and
  6 above would have been caught on day one.
- The "verify in chat" vs "verify in batch" confusion around memory
  recall (see #102) came from loose wording in the plan. Acceptance
  tests should name the exact log line and the exact place it appears.
- Retro discipline: this file is a week late.

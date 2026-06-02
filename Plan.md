# Tessera Build Plan

> From frontend-only MVP → working paper-trading pilot with real LLM theses
> for self + 2 friends-and-family users. **6 weeks part-time, 3–4 weeks
> full-time.** Solo developer scope. Compressed-pace plan — each phase
> assumes focused, uninterrupted execution.

---

## 0. Where we are today (baseline)

**Phase A is complete.** ✅ Updated 2026-05-18.

**Built and shipped:**
- Next.js 14 frontend with 4 routes (`/`, `/proposals`, `/dashboard`, `/how-it-works`) + Vercel-Cron-ready
- Claude-design system (cream + coral + ink palette, Fraunces serif, JetBrains Mono) + inline mosaic SVG mark
- 4 persona personas (Warren, Cathie, Ray, Peter) with photos, bios, and `personalities.md` system prompts
- Slide-over persona detail with Thesis ↔ Chat toggle
- Mock chat engine (keyword-matched response banks per persona) — frontend still reads this
- Mock performance series, proposals, reports — frontend still reads this
- **Python worker** (apps/worker) — FastAPI skeleton, SQLAlchemy + psycopg3, structlog
- **Neon Postgres** live with TimescaleDB + pgvector, 14 tables, 001_init.sql applied
- **5 production ingestors**: Alpaca EOD, Coinbase EOD, FRED macro, FMP fundamentals, NewsAPI
- **51-ticker universe** spanning sectors each persona cares about
- **Deterministic feature builder** — ret_*, vol_30d, rsi_14, sma_{20,50}, volume_z. 13/13 hypothesis tests pass.
- **Daily orchestrator** (`ingest_daily.py`) — 6 sequential steps, idempotent, CLI flags
- **Vercel Cron endpoint** (`/api/cron/daily`) — edge runtime, Bearer-auth via `CRON_SECRET`, schedule `30 21 * * 1-5`
- **Connection smoke test** + **SPY canary** (0.49 bps vs Yahoo)

**Production Neon state:**
| Table | Rows |
|---|---|
| `ohlcv_1d` | ~14,000 |
| `ticker_features` | 13,983 |
| `macro_series` | 566 |
| `fundamentals` | 255 |
| `news` | 555 |

**Still missing (Phase B onwards):**
- No LLM calls yet (chat + theses both mocked)
- No real auth (assumes `jshin`)
- No broker integration (Alpaca only used for market data, no trading client)
- No paper-trading engine
- No risk gateway
- Cloud Run worker not yet deployed (laptop runs the orchestrator; Vercel Cron returns noop)
- Frontend still reads mock data (deferred — Phase B will inject real theses first)

This plan takes the project from **demo → Phase A done → operational pilot**.

---

## 1. Guiding principles for the build

1. **Ship in two-week slices.** Every slice ends with something deployable and verifiable in production.
2. **Paper-first, always.** No live execution until lawyer-cleared. Same code path; only the `ExecutionAdapter` changes.
3. **Numbers in Python, narrative in LLM.** Never let the model compute a price or weight.
4. **One-way data flow.** Data plane → Agent plane → Decision plane → Execution plane → User plane. No backward calls.
5. **Feature-flag everything risky.** LLM calls behind `feature.real_llm`. Live trading behind `feature.live_trading`. Default off.
6. **Backtest before trusting.** Before declaring a persona "done", replay 30 days of past data and inspect outputs manually.
7. **Cost dashboard from day one.** If we can't see what we're spending on LLM, we can't control it.

---

## 2. Phase map

| Phase | Week(s) | Goal | Deployable artifact |
|---|---|---|---|
| **A** | 1 | Data backbone | Cron-driven ingestion writing to Neon |
| **B** | 2–3 | Real LLM theses | Each persona writes daily Sonnet 4.6 thesis |
| **C** | 4–5 | Paper execution + attribution | Real Sharpe/MDD on leaderboard from paper P&L |
| **D** | 6 | User auth + portfolios | 3 friends-and-family users following personas |
| **E** | 6 (parallel) | Compliance review | Written lawyer advice on file |
| **F** | 7+ | Live trading (optional) | Self running live; F&F only if E clears it |

Hard dependencies: A → B → C → D. E runs in parallel with D. F requires E.
Phases A–D are 6 weeks total. Compression vs. the earlier 12-week plan
comes from collapsing intra-phase weeks (no separate "infrastructure"
and "implementation" weeks — they ship together).

---

## 3. Phase A — Data backbone (Week 1) — ✅ DONE 2026-05-18

**Goal**: Real market data, fundamentals, macro, and news flowing into Neon. Frontend reads from API routes instead of mock files.

**Actual result**: All ingestors + feature builder + daily orchestrator + Vercel Cron endpoint shipped. End-to-end production verification on 2026-06-01: 14,523 ohlcv rows · 300 fundamentals · 646 macro · 1,648 news · 14,470 features — all 6 steps pass, 0 failures.

**Carried over to Phase B Week 2** (not Phase A blockers): GCP/Cloud Run deploy, Sentry DSN, SEC EDGAR ingestor, frontend mock→/api swap. See `[→]` markers below for each.

### Infrastructure (Mon–Tue) — ✅
- [x] Create Neon project (free tier), install TimescaleDB + pgvector extensions
- [→] Create GCP project; enable Cloud Run + Cloud Tasks + Secret Manager — **moved to Phase B Week 2** (orchestrator runs locally for Phase A; Cloud Run needed once `WORKER_WEBHOOK_URL` is wired)
- [x] Restructure repo into monorepo:
  ```
  apps/web/        # existing Next.js
  apps/worker/     # new Python (FastAPI for HTTP-triggered jobs)
  packages/shared/ # Pydantic schemas, Alpaca adapter, persona loader
  ```
- [x] Schema migration v1 (chose plain SQL via psql):
  ```
  ohlcv_1d          (ticker, date, ohlcv, vwap, source)
  fundamentals      (ticker, period, income_stmt, balance_sheet, cash_flow as jsonb)
  filings           (id, ticker, type, date, raw_gcs_uri, text)
  macro_series      (series_id, date, value)
  news              (id, ts, source, tickers[], title, body, embedding vector(1536))
  ticker_features   (ticker, ts, ret_1d, ret_30d, fcf_yield, peg, rsi_14, …)
  analyst_reports   (id, persona_id, ts, inputs_hash, parsed jsonb, raw_response, cost_usd)
  persona_portfolios(persona_id, ts, cash, positions jsonb, total_value)
  persona_trades    (id, persona_id, ts, ticker, side, qty, price, report_id)
  persona_performance(persona_id, date, pnl_day, pnl_cum, return_cum, sharpe_30d, mdd_30d)
  ```
- [→] Sentry on web + worker — **moved to Phase B Week 2** (scaffolded in config; only DSN registration remains)

### Ingestors + feature builder — ✅
- [x] **Alpaca EOD ingestor** — 51 tickers (US equities + ETFs); chunked, idempotent ON CONFLICT
- [x] **Coinbase EOD ingestor** — BTC, ETH (300-candle paginated windows, public API)
- [x] **FMP fundamentals ingestor** — `/stable/*` endpoints (legacy `/api/v3` returns 403); 30-day cache check in orchestrator
- [→] **SEC EDGAR filings ingestor** — **moved to Phase B Week 2** (`filings` table schema exists; not yet populated. Phase A had enough signal from OHLCV + fundamentals + news to validate the pipeline)
- [x] **FRED macro ingestor** — 20 series (yields, breakevens, CPI/PCE, unemployment, M2, Fed bs, VIX, USD)
- [x] **NewsAPI ingestor** — 49 equities, "TICKER OR Company Name" query, in-process dedup. Embeddings deferred to Phase B (need Anthropic/Voyage or self-hosted bge-small).
- [x] **Feature builder** (`features/compute.py`): deterministic pandas/numpy; ret_{1d,5d,30d,90d,1y}, vol_30d, rsi_14, sma_{20,50}, volume_z
- [x] **Property-based tests** on feature builder — 13 hypothesis tests pass
- [x] **Canary asserts**: SPY 1y return vs Yahoo → **0.49 bps diff** (threshold 100 bps)
- [x] **Vercel Cron**: declared in `apps/web/vercel.json` (`30 21 * * 1-5`), endpoint at `/api/cron/daily` (edge runtime, Bearer auth via `CRON_SECRET`); pending `WORKER_WEBHOOK_URL` once Cloud Run is deployed
- [→] Frontend swap: `lib/mock/performance.ts` → `/api/performance` route — **moved to Phase B Week 3** (sequence: real theses must exist first, then swap mock for non-empty UI)

**End-to-end production results** (one full daily orchestrator run on Neon):
| Step | Rows | Time |
|---|---|---|
| ohlcv_equity | 1,020 (delta upsert; cumulative ~14,000) | 2.4s |
| ohlcv_crypto | 62 | 0.8s |
| macro | 566 | 16s |
| fundamentals | 255 | 7.7m (first run; 30-day cache after) |
| news | 555 | 14s |
| features | 13,983 | 8.4s |

**Lessons from Phase A**:
- FMP legacy `/api/v3/*` returns 403; must use `/stable/*` with `?symbol=` param. Doc'd in `check_connections.py`.
- httpx default logger prints full URL incl. `?apikey=` — leaked NewsAPI + FMP keys before fix. Now silenced to WARNING in `logging.py`. Two keys had to be rotated.
- SQLAlchemy + Neon connection string needs `postgresql+psycopg://` prefix; raw `postgresql://` defaults to psycopg2 driver which we don't install. Handled in `db._normalize_url`.
- `unnest(:tickers::text[])` collides with psycopg param marker — moved freshness filter from SQL to Python in `_step_fundamentals`.

### Acceptance criteria
- ✅ All 4 persona cards show metrics computed from real data, not seeded random
- ✅ Cumulative return chart matches S&P 500 actual performance over visible window
- ✅ One full daily cycle (ingest → features) runs in < 10 min
- ✅ Worker survives a re-run without duplicating rows (idempotent)

### Blockers / risks
- Alpaca free tier is IEX-only — accept the limitation for pilot
- FMP free tier rate limits — may need $14/mo starter

---

## 4. Phase B — Real LLM theses (Weeks 2–3)

**Goal**: Each persona writes a real Sonnet 4.6 thesis daily. Chat replaces mock engine with real Anthropic call.

### Week 2 — Persona runner + full desk
- [ ] **Persona loader**: parse `personalities.md` sections per persona, cache in memory
- [ ] **Prompt assembler**: persona spec + feature snapshot + memory recall → prompt
- [ ] **Pydantic models**: `AnalystReport`, `Proposal` with full field validation
- [ ] **Anthropic SDK wrapper**: typed call, retry on schema failure (1×), log tokens + cost
- [ ] **Citation validator**: every `cited_news_ids` must resolve in `news` table
- [ ] **Universe screen** (Haiku 4.5): per persona, narrow ~500 → top 30
- [ ] **Hybrid selection**: ∪ with mechanical primary-metric top-30 per persona — see risk: *Haiku false negatives*
- [ ] **Screen audit job** (weekly): Sonnet re-evaluates 10 randomly-sampled rejected names; alert if any score ≥ inclusion threshold
- [ ] **`screen_promotion_rate` dashboard**: target band 30–80%
- [ ] **Deep thesis** (Sonnet 4.6): on shortlist only
- [ ] **Prompt caching**: persona spec (~3K tok) marked `cache_control: ephemeral`
- [ ] **pgvector recall**: surface prior 5 theses on same ticker via embedding similarity
- [ ] **Cost logging**: every call → Grafana metric `tessera_llm_cost_usd{persona, stage}`
- [ ] **First sanity check**: Warren writes a real thesis on AAPL. Manual review.

#### Carried over from Phase A — 정우 owned these (offloaded from 윤채/예슬 for Week 2)
- [x] **Sentry DSN registration** on web + worker — shipped 2026-06-01. Both `tessera-web` + `tessera-worker` projects live, errors-only (no perf traces / replays) for free-tier cost guard. End-to-end verified via `/api/sentry-verify` (now removed). Pattern: explicit `Sentry.captureException` + `flush()` in Next 14 route handlers (auto-instrumentation isn't reliable there).
- [x] **GCP project + Cloud Run + Cloud Tasks + Secret Manager** — shipped 2026-06-01. Project `tessera-498200` (us-east1), Artifact Registry repo `tessera`, service account `tessera-worker` with `roles/secretmanager.secretAccessor`, 9 secrets in Secret Manager. Worker container at `tessera-worker-ffr7g3a76a-ue.a.run.app`. Vercel Cron now triggers Cloud Run via `WORKER_WEBHOOK_URL` and the full 6-step ingest runs autonomously — verified Neon row counts incremented end-to-end. Implementation notes captured in `docs/adr/006-vercel-cloud-run-split.md`.
- [ ] **SEC EDGAR filings ingestor** (정우) — populate `filings` table (10-K, 10-Q text); plug into Warren/Peter context. Frees 예슬 to focus on features + risk gateway prep for Phase C. _In progress._

### Week 3 — Chat + backtest + hardening
- [ ] **Chat backend**: `/api/chat/[personaId]` assembling 6-part system prompt
  (persona spec + book + recent reports + relevant features + history + user msg);
  stream Anthropic response via SSE; wire `analyst-chat.tsx` to consume stream
- [ ] **Backtest harness**: replay last 30 days of features, generate 30 days of
  theses, manually review 10 random samples per persona for voice + reasoning quality
- [ ] **Hard rule enforcement**: per-persona validators (e.g., Warren cannot output `target_weight > 0.18`)
- [ ] **Hallucination canary**: 5 known-bad prompts run weekly, all must be rejected
- [ ] **Cost cap**: alert in Grafana if daily LLM cost > $10
- [ ] **Frontend swap** (한솔, carried over from Phase A): `lib/mock/performance.ts` → `/api/performance`; same for thesis + portfolio reads. Now safe because real theses exist.

**Compression note**: previously three weeks (runner / desk / chat). Now two
weeks. Risk: backtest review is rushed. Mitigation: review sample size from 10
to 5 per persona; defer voice tuning to post-launch iteration.

### Acceptance criteria
- ✅ Open Warren in UI → see real thesis written today, with citations linking to real news rows
- ✅ Open chat with Cathie → real Sonnet response, in her voice
- ✅ Cost dashboard shows < $5/day on average
- ✅ Backtest of 30 days × 4 personas shows < 2% schema-validation failure rate
- ✅ 0 hallucinated tickers reached the UI in 30-day backtest

### Open decisions to resolve here
- **Chat model**: Sonnet 4.6 always (simpler, ~$0.012/msg) vs. fine-tuned Haiku per persona (more expensive to set up, ~$0.001/msg, stronger voice). **Recommendation: Sonnet 4.6 for pilot, revisit when chat volume justifies fine-tune.**

---

## 5. Phase C — Paper execution + attribution (Weeks 4–5)

**Goal**: Each persona's portfolio executes in paper. Daily P&L tracked. Leaderboard shows real Sharpe/MDD.

### Week 4 — Risk gateway + paper engine + mark-to-market
- [ ] **Risk gateway** (`tessera/risk/gateway.py`): ticker-exists, single-name cap, sector cap, parametric VaR, drawdown floor. Pure Python.
- [ ] **PaperEngine** (`ExecutionAdapter` impl): diff vs current positions → orders → fill at next-day open
- [ ] **Order ledger** (orders, positions, ledger): full audit trail
- [ ] **LISTEN/NOTIFY**: `analyst_reports` INSERT → Cloud Run job evaluates rebalance
- [ ] **EOD mark-to-market**: recompute `persona_portfolios.total_value` daily
- [ ] **Persona performance writer**: nightly pnl_day, pnl_cum, sharpe_30d, mdd_30d, hit_rate

### Week 5 — Frontend wire-up + baseline backtest + weight-distribution telemetry
- [ ] **Leaderboard tab** reads from `persona_performance` (delete mock)
- [ ] **Cumulative return charts**: read real persona equity curve
- [ ] **Attribution breakdown**: ticker-level contribution to each persona's MTD return
- [ ] **Backtest mode**: replay 90 days → simulate 90 days of paper trades → baseline Sharpe/MDD
- [ ] **Weight distribution telemetry**: weekly histogram per persona — alert on bimodal distribution at cap (see risk: *mode collapse*); decide by end of week whether to refactor to conviction-only schema
- [ ] **Push notification on rebalance**: FCM → browser
- [ ] **Sentry alert**: paper engine error → page within 5 min
- [ ] **Skeleton/error states**: all frontend reads have loading + error UIs
- [ ] **Quant data integrity gates**: point-in-time guard, stale-data check, adjusted-price policy, and invalid-feature handling before leaderboard/backtest metrics are written
- [ ] **Leakage tests for backtest mode**: ensure feature_date never overlaps with target_return_window and no post-rebalance data is used

**Compression note**: previously three weeks. The biggest sacrifice is the
length of real-life paper track record collected by end of Phase C — only
days, not weeks. The 90-day backtest baseline becomes the credibility anchor
instead of real elapsed paper time.

### Acceptance criteria
- ✅ Leaderboard shows real 30-day Sharpe and MDD per persona
- ✅ Cumulative return chart on landing page matches sum of paper trade P&L
- ✅ Backtest 90-day Sharpe is within expected range per archetype (Warren ~1.3, Cathie ~0.9, Ray ~1.5, Peter ~1.4)
- ✅ 0 risk-gate violations slipped to paper execution

---

## 6. Phase D — User auth + personal portfolios (Week 6)

**Goal**: 3 friends-and-family users sign up, each follows a persona on their own paper account.

### Tasks
- [ ] **Firebase Auth**: Google SSO, callback to Next.js middleware
- [ ] **Users table** in Neon: `firebase_uid` ↔ Tessera user, preferences
- [ ] **"Follow this persona" CTA** on persona detail sheet
- [ ] **user_portfolios table**: (user_id, persona_id, started_at, starting_capital, current_positions)
- [ ] **Mirror engine**: when persona trades, mirror in every follower's account
- [ ] **Dashboard reads real positions**: delete mock in `/dashboard`
- [ ] **Personal P&L diverges** from persona P&L based on follow start + capital
- [ ] **FCM push** when followed persona rebalances
- [ ] **Onboard 3 F&F users**: self + 2 family/friends, each on a different persona

**Compression note**: previously two weeks. The social feed feature is
deferred to post-launch. Auth + mirror engine + onboarding ship in one week.

### Acceptance criteria
- ✅ 3 real users in production with active paper portfolios
- ✅ Each user's dashboard shows their own P&L, not the persona's
- ✅ Push notification fires within 30s of rebalance
- ✅ Lawyer consult is scheduled (Phase E)

---

## 7. Phase E — Compliance review (Week 6, runs parallel to D)

**Goal**: Written advice from a US securities lawyer on file before scope expands.

### Tasks
- [ ] Schedule 30–60 min consult with US securities lawyer (~$300–500)
- [ ] **Prepare brief** (one-pager) covering:
  - What Tessera publishes (theses + portfolios)
  - Who has accounts (self + 2 F&F)
  - Paper-trading only, no custody, OAuth for any live
  - Marketing language we use ("not investment advice")
  - Where we want to go (live for F&F, then maybe public)
- [ ] **Specific questions to ask**:
  1. Can F&F run paper trading without RIA registration?
  2. What threshold of users / behavior triggers RIA requirement?
  3. Can we move F&F to live trading? What disclaimer / IAQ needed?
  4. Publisher's exclusion (Lowe v. SEC) — does our chat-with-analyst feature break it?
  5. State Blue Sky implications for users in different states
- [ ] **Apply recommendations**: update terms of service, marketing copy, onboarding flow
- [ ] **Document decision**: clear go/no-go on Phase F

### Acceptance criteria
- ✅ Written lawyer advice in repo (`compliance/lawyer-memo-2026-XX.md`, gitignored)
- ✅ Decision recorded: which user cohorts can go live, which cannot
- ✅ Marketing copy reviewed against advice

---

## 8. Phase F — Live trading (Week 7+, optional)

**Goal**: Flip live flag for self only. F&F only if Phase E cleared.

### Tasks
- [ ] **AlpacaLiveAdapter** implementation, behind `feature.live_trading` flag
- [ ] **OAuth flow**: Alpaca authorize → callback → token storage (encrypted in Firestore)
- [ ] **Order confirmation modal**: every order requires user click to confirm
- [ ] **Kill switch UI**: 1-click → Temporal workflow → close all positions
- [ ] **Self runs live for 7 days** with full monitoring
- [ ] Compare live fills vs. paper fills on same day → quantify slippage
- [ ] Only after self proves stable: enable for F&F users (if lawyer cleared)

### Acceptance criteria
- ✅ Self running live successfully for 1+ week
- ✅ Slippage between paper and live < 30 bps per round trip
- ✅ Kill switch tested and works in < 60s
- ✅ Zero orders sent without explicit user confirmation

---

## 9. Cross-cutting workstreams (run throughout)

### Observability
- **From Week 1**: Sentry on web + worker
- **From Week 2**: Grafana Cloud — LLM cost, ingestor lag, paper-fill error rate
- **From Week 4**: Simple `/status` page (last ingest, last persona run, paper engine health)
- **From Week 6**: Sentry alerts → email; cost alerts at $5/day, $10/day, $20/day thresholds

### Secrets management
- Anthropic key, Alpaca key (when live), FMP key, NewsAPI key → GCP Secret Manager
- Firebase Admin SDK → Vercel env var (encrypted)
- **Never commit any key.** Pre-commit hook checks for common patterns.

### CI / quality
- **From Week 1**: GitHub Actions running `npm run typecheck` + `npm run lint` on every PR
- **From Week 2**: Python `ruff` + `mypy --strict` on worker
- **From Week 4**: smoke test that hits `/api/health` on every PR

### Documentation
- Keep `architecture.md` and `personalities.md` in sync with code; treat as ADRs
- After each phase, write a short retro note in `docs/retro-phase-X.md`
- Update `Plan.md` (this file) if scope changes

---

## 10. Open decisions

These don't block Phase A but should be decided by the end of Phase B.

| Decision | Options | Recommendation | Decide by |
|---|---|---|---|
| Manager curation | (a) ship as-built (4 portfolios side-by-side) (b) add 5th persona "Mara" that curates into 3 named portfolios | **(a) for pilot, revisit at user count > 20** | End of B (wk 3) |
| Chat model | (a) Sonnet 4.6 always (b) fine-tuned Haiku per persona | **(a)** until chat volume > 500 msg/day per persona | End of B (wk 3) |
| Cathie crypto exposure | (a) equity proxies only (COIN, MSTR) (b) spot BTC/ETH via Coinbase | **(a) for pilot**, (b) requires Coinbase OAuth + additional disclosures | End of B (wk 3) |
| Backtest window | (a) rolling 90d (b) fixed 2024-01 → 2025-12 | **(b)** — reproducible baseline that everyone can compare against | Start of C (wk 4) |
| Persona count for pilot | (a) all 4 (b) Warren + Cathie only | **(a)** if budget allows, else (b) | Start of A (wk 1) |
| Weight decision authority | (a) LLM outputs `target_weight` directly (current schema) (b) LLM outputs `conviction ∈ [0,1]`, Python maps to weight | **Start with (a); refactor to (b) if mode-collapse telemetry flags it.** (b) is architecturally cleaner but reduces LLM-side explainability. | End of C (wk 5) |
| Screen funnel width | (a) Haiku promotes top 30 (current spec) (b) top 60 (recall-tuned) (c) hybrid: Haiku ∪ mechanical metric top-30 | **(c)** — belt and suspenders. Costs ~30% more Sonnet calls but cuts false-negative risk meaningfully. | Start of B (wk 2) |

---

## 11. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Anthropic rate limits during batch | Med | High | Stagger persona calls (15s offset), exponential backoff on 429 |
| Alpaca paper fills differ from live | Med | Med | Validate paper fill price against EOD close ± 50 bps; alert on outliers |
| Hallucinated ticker reaches UI | Low | Critical | Risk gateway hard check + Sentry alert on rejection event |
| LLM cost exceeds budget | Med | Med | Daily cost cap, auto-pause batch if 2× previous day's spend |
| Securities lawyer says we need RIA | Med | High | Phase F stays self-only; F&F remain paper indefinitely |
| Persona thesis quality poor | Med | High | Mandatory 30-day backtest review before declaring B done; tune `personalities.md` |
| Neon free tier exhausted | Low | Low | Move to paid tier ($19/mo) at 80% usage |
| pgvector recall returns irrelevant theses | Med | Low | Tune similarity threshold; fall back to recency-only if k=0 above threshold |
| Vercel function timeout (60s) on LLM call | High | Med | Move chat to a Cloud Run streaming endpoint; never call Anthropic directly from Vercel |
| User confused by 4 disagreeing portfolios | Med | Med | UX research with F&F users in Phase D; consider Manager curation if confirmed |
| **Feature builder bug propagates as LLM-blessed thesis** — Python computes `ret_30d` wrong, LLM writes confident thesis defending the wrong number | Med | High | Property-based tests on `compute_features`; weekly spot-check of 10 random feature rows vs hand calc; LLM output must `cite_features_used`, making post-mortem traceable; canary asserts (e.g., SPY 1y return must match Yahoo within 10 bps) |
| **Haiku screen filters out genuine alpha (false negatives)** — 500→30 funnel creates permanent selection bias the desk can never recover from | Med | Med | (1) Recall-tuned screen prompt, promote top 60 not top 30 (2) Hybrid selection: union of Haiku top-30 ∪ mechanical primary-metric top-30 per persona (Warren = FCF yield, Cathie = revenue CAGR, etc.) (3) Weekly audit job: Sonnet re-evaluates 10 random rejected names; if any score high, revise screen prompt (4) Per-persona ground-truth eval set for regression detection (5) Track `screen_promotion_rate`; sweet spot 30–80% — outside that, retune |
| **Mode collapse: LLM anchors `target_weight` at the cap** — model treats 18% cap as "max conviction default", producing portfolios with 4–5 names all at 17–18% (disguised concentration) | High | High | **Detection** in Phase C: weekly weight-distribution telemetry per persona; alert on bimodality (KL divergence vs expected long-tail). **Fix order** (apply if detected): (1) **Best**: remove `target_weight` from LLM output schema entirely; LLM outputs `conviction ∈ [0,1]`, Python maps to weight deterministically (`w = clamp(conviction × 0.20, 0, cap)`). Eliminates anchoring at the source. (2) **Interim**: discrete weight enum `{0.03, 0.05, 0.08, 0.10, 0.13, 0.16}` — explicitly exclude cap value from selectable options. (3) **Weak**: prompt-level anti-anchor language. Don't rely on this alone. |

---

## 12. Definition of done — MVP launch

The pilot is "done" (ready to consider expansion or shutdown) when:

- [ ] **All 4 personas** writing real Sonnet 4.6 theses daily, validated
- [ ] **30+ days** of paper P&L track record, accurate Sharpe/MDD displayed
- [ ] **Self** running paper successfully for 30+ days, no manual intervention required
- [ ] **3 F&F users** onboarded, each following a different persona, with their own dashboard
- [ ] **Lawyer consult** complete; written advice on file
- [ ] **Cost stable** under $200/mo for 4 weeks
- [ ] **One write-up** (blog post or talk) explaining the approach publicly
- [ ] **No open Sev-1 bugs** for 14 consecutive days
- [ ] **Decision documented** on whether to expand to public users, go live with F&F, or pivot

---

## 13. Time estimates and resourcing

**Solo developer, part-time (10h/week)**: ~12 weeks total to MVP-launch DoD
**Solo developer, full-time (40h/week)**: ~3–4 weeks
**Two developers (one full-stack, one ML/data)**: ~2–3 weeks

Critical-path items: Phases A → B → C run serially. D, E can parallelize with C
if a second person is available — that's the path to the lower bound. At this
compressed pace, expect to **skip features rather than slip dates**: the
"Compression notes" under each phase call out what gets cut first.

---

## 14. What this plan deliberately doesn't do

- **No mobile app.** Web responsive is enough for pilot.
- **No real-time intraday signals.** Daily batch is the design.
- **No multi-currency support.** USD only.
- **No tax-lot accounting.** Just simple P&L per position.
- **No bring-your-own-LLM.** Anthropic Claude only.
- **No options, futures, or margin.** Cash equities + crypto spot only.
- **No multi-tenant white-label.** Single Tessera product.
- **No mobile-style push for chat.** FCM only on rebalance events.

Each of these could be a future phase. Keeping them out of pilot scope is the discipline that lets us ship.

---

## Versioning

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-05-18 | Initial plan covering A → F phases, 12-week timeline, F&F pilot scope |
| 0.2 | 2026-05-18 | Timeline scaled by ½: 12 weeks → 6 weeks core (Phases A–D), F at wk 7+. Per-phase "Compression notes" added explaining what gets cut. |
| 0.3 | 2026-05-18 | Added 3 risks from AI study group review: (1) feature builder bug propagating as LLM-blessed thesis, (2) Haiku screen false negatives, (3) mode collapse — LLM anchoring weight at cap. Added 2 open decisions (weight authority schema, screen funnel width). Wired specific tasks into Phase A (property tests + canary asserts), Phase B (hybrid selection + audit + promotion-rate dashboard), Phase C (weight-distribution telemetry). |
| 0.4 | 2026-05-18 | **Phase A complete.** Marked tasks done in Section 3 with actual production metrics (1,020 ohlcv_equity rows, 13,983 features, SPY canary 0.49 bps, etc.). Updated baseline (Section 0) to reflect new monorepo + worker + 5 ingestors. Added "Lessons from Phase A" subsection capturing 4 real footguns hit (FMP legacy endpoint deprecation, httpx URL logging leak, SQLAlchemy psycopg2 default, `unnest(:tickers::text[])` SQL collision). Phase A took 1 working session, well under the 1-week budget. |

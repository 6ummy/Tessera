# Tessera Build Plan

> From frontend-only MVP → working paper-trading pilot with real LLM theses
> for self + 2 friends-and-family users. **6 weeks part-time, 3–4 weeks
> full-time.** Solo developer scope. Compressed-pace plan — each phase
> assumes focused, uninterrupted execution.

---

## 0. Where we are today (baseline)

**Phase A + B complete; Phase C Week 4 core LIVE.** ✅ Updated 2026-06-12.

**Phase C Week 4 — shipped 2026-06-11/12** (see "2026-06-11 codebase
audit" subsection in §5 + `docs/improvement-plan-2026-06-11.md`):
- **Audit Step 0–2** (#90, #93): OHLCV canonical-day fix (P0-1 — mixed-source
  duplicates had silently halved every row-window feature horizon; migration
  006 + dedup + SPY canary back to 2.62 bps), `/api/proposals` v2 aggregator
  fix (ghost positions), yfinance promoted to core dep, CI workflows (ruff
  0-backlog + pytest blocking), gitleaks pre-commit, ingest advisory lock,
  chat abuse guards + $2 chat-only budget pool, nightly SPY canary step,
  `--no-cpu-throttling`.
- **Risk gateway** (#94): thin validator inside the construction retry loop —
  universe membership, sum=1.0, single-name + sector caps (sector was
  prompt-only before). VaR/drawdown wait for paper positions.
- **PaperEngine v1** (#95, #96): 14th `ingest_daily` step,
  `FEATURE_PAPER_EXECUTION=true` in prod. Fills latest unexecuted book at
  next bar open, EOD mark-to-market, `persona_performance` writer, 4 ×
  $100K paper bootstrap. **First run expected 2026-06-12 21:30 UTC cron** —
  verify `persona_trades` / `persona_portfolios` / `persona_performance`
  rows after.
- `CLAUDE.md` added (session catch-up notes for Claude Code).

Previous baseline (2026-06-06) follows:

**Phase A — shipped 2026-05-18:**
- Next.js 14 frontend with 4 routes (`/`, `/proposals`, `/dashboard`, `/how-it-works`) + Vercel-Cron-ready
- Claude-design system + 4 persona personas (Warren / Cathie / Ray / Peter) with photos, bios, `personalities.md` system prompts
- **Python worker** + **Neon Postgres** (TimescaleDB + pgvector), 14 tables
- **7 production ingestors**: Alpaca, Coinbase, FRED (37 series), FMP, NewsAPI, SEC EDGAR (10-K/10-Q + GCS HTML), SEC XBRL companyfacts
- **51-ticker universe** + deterministic price feature builder (ret_*, vol_30d, rsi_14, sma_*, volume_z)
- **Daily orchestrator** + **Vercel Cron** endpoint (Bearer-auth, `30 21 * * 1-5`)
- **Historical backfill** (`backfill_history.py`) — ~325K rows pre-shipped so backtest harness has 6yr equities / 11yr crypto / 9yr SEC fundamentals from day one

**Phase B Week 2 — shipped 2026-06-02 / -03:**
- **Cloud Run worker deployed** (Dockerfile + cloudbuild.yaml at repo root, prod cron live)
- **Sentry DSN** registered on web + worker (errors-only)
- **LLM pipeline end-to-end**: `persona_loader` + `prompt_assembler` + `anthropic_runner` + `citation_validator` + Pydantic `AnalystReport`/`Proposal` schemas — Sonnet 4.6 deep thesis, prompt caching on persona spec, 2-attempt retry with feedback, cost logged per call to `llm_call_log` + hard daily cap via `check_daily_budget()`
- **Ray RegimeProbabilities runner** — parallel `RegimeReport` schema (ETF allocations, regime probabilities), discriminated-union persistence into same `analyst_reports` table via `persona_id='ray'`
- **All 4 personas writing real Sonnet 4.6 theses verified** (manual CLI; cron auto-trigger pending `persona_batch.py`)
- **Quant `fcf_yield`** shipped — TTM cumulative-YTD decomposition + FX (TWD/EUR/etc.) + cross-validated market cap; 31/42 tickers writing fcf_yield in band of independently-computed real values

**Phase B Week 3 — shipped 2026-06-04 / -05:**
- **Backtest harness** (`jobs/backtest_harness.py`) — point-in-time replay over N days × M personas × K tickers, all `fetch_inputs` queries upper-bound on `as_of`, persists to separate `backtest_reports` table, schema-fail rate vs. 2% acceptance gate, honors daily cap + per-run `--max-cost`. **Live 60-cell + 18-cell runs both PASSed** (1.67% then 0% fail rate after follow-ups)
- **pgvector recall** — Voyage AI embeddings (1024-dim), `persist_analyst_report` writes `persona_memory` rows best-effort, `fetch_memory_recall` switches between similarity (`<=>` cosine) and recency at runtime
- **LLM robustness pass** — `personalities.md` `confidence`→`conviction` rename (silent-signal-loss fix), `JSONDecoder.raw_decode` parser absorbs trailing chatter (Cathie scenario narration), `_retry_guidance_for` pattern-matches the validation error and gives the LLM a SPECIFIC corrective instruction
- **Leakage tests** for backtest mode — mock-session unit tests prove `fetch_inputs(as_of=X)` never emits a query without an `as_of` upper-bound

**Phase C Week 4 Quant precursor — shipped locally 2026-06-06:**
- **Quality / growth feature pass** — `features/compute.py` now writes
  `peg`, `eps_cagr_3y`, `debt_to_equity`, `gross_margin`,
  `gross_margin_trend`, `market_cap_usd`, and `operating_margin` to the
  latest `ticker_features` row per ticker. The path reuses the `fcf_yield`
  scaffold: pure functions, loader extension, latest-row upsert, and tests.
  `004_quality_features.sql` is idempotent and backfills missing schema
  columns with `ADD COLUMN IF NOT EXISTS`.

**Production Neon state (approx, 2026-06-05):**
| Table | Rows | Note |
|---|---|---|
| `ohlcv_1d` | ~250K | 20-yr depth via yfinance backfill |
| `ticker_features` | ~260K | 6yr × 53 tickers, price/momentum history + latest quality features |
| `macro_series` | ~237K | full FRED history |
| `fundamentals` | ~7,400 | FMP + SEC XBRL merged, 39/42 ticker coverage |
| `news` | ~2.5K+ | growing daily |
| `analyst_reports` | ~30 | live + smoke runs |
| `backtest_reports` | ~80 | from 60+18+1 cell runs |
| `persona_memory` | ~30 | one row per proposal, embedded best-effort |

**Still missing (Phase B Week 3 end → Phase C):**
- ~~`persona_batch.py`~~ ✅ shipped 2026-06-05
- ~~Chat backend~~ ✅ shipped 2026-06-05 (backend + frontend SSE consumer)
- ~~Frontend swap (reports + proposals)~~ ✅ shipped 2026-06-05
- ~~More Quant features (PEG / EPS CAGR / D-E / gross margin)~~ ✅
  shipped locally 2026-06-06; remaining Phase C work is precision hardening
  and risk-gateway consumption.
- **No paper-trading engine, no risk gateway** — Phase C Week 4
- **performance.ts + portfolio.ts mocks** — blocked on Phase C paper engine populating `persona_performance`

**🏁 Phase B ENDED 2026-06-05.** All §4 acceptance criteria 🟢. Next: Phase C (paper execution + risk gateway).
- **No real auth** (assumes `jshin`) — Phase D
- **Grafana cost dashboard** — `llm_call_log` table is the source of truth; visualization deferred to Phase C observability work

This plan takes the project from **demo → Phase A done → Phase B done → Phase C paper engine + risk gateway**.

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
- [x] **FRED macro ingestor** — 37 series (yields, breakevens, CPI/PCE, unemployment, M2, Fed bs, VIX, broad USD; **expanded 2026-06-02**: 9 FX pairs, WTI + Brent + nat gas + jet fuel, copper + wheat, HY + IG credit spreads)
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

### Week 2 Quickstart — working with the data we already have

Phase A wired the entire data plane. **Quant (예슬, 준원), LLM Pipeline (한솔), and Frontend (한솔, 윤채) work on top of what's already there** — nobody needs to wait on infra.

#### ✅ Already done by 정우 — DO NOT redo

You'll see this stack referenced everywhere. It's all live. Coworkers don't sign up, deploy, or configure any of it.

| Component | State | Why it matters to you |
|---|---|---|
| **Neon Postgres** (`tessera-498200` region us-east-1, 14 tables) | ✅ live, applied `001_init.sql` | Connect with `DATABASE_URL` from KakaoTalk pin — just read |
| **Vercel deploy** (`tessera-ruby.vercel.app`) | ✅ live | Frontend you'll wire in Week 3 |
| **Vercel Cron** (`30 21 * * 1-5`, weekday 21:30 UTC) | ✅ scheduled | Triggers the daily 7-step ingest automatically — you don't run it |
| **Cloud Run worker** (`tessera-worker`, us-east1, autoscale 0–2) | ✅ deployed | Where the cron fires; runs the ingest job; you don't touch its config |
| **GCP project** (`tessera-498200`) + Artifact Registry + Service Account + 10 Secret Manager secrets | ✅ set up | Production credentials live here; you'll never need to log in to GCP for normal Week 2 work |
| **6 ingestors** (Alpaca, Coinbase, FRED, FMP, NewsAPI, SEC EDGAR) | ✅ shipped to Cloud Run | They run daily; data lands in Neon overnight |
| **Sentry** (web + worker projects, errors-only) | ✅ wired | Unhandled exceptions show up automatically; no DSN paste needed |
| **GCS bucket** `gs://tessera-raw/edgar/` (raw 10-K/10-Q HTML) | ✅ created | Only matters if you work on the EDGAR parser — most don't need access |
| **API keys** (Anthropic, Alpaca, FMP, FRED, NewsAPI) | ✅ in 1) Secret Manager (prod) 2) KakaoTalk pin (local dev) | Copy to your `.env`, do not generate new keys |

**The one thing 정우 cannot do for you**: `gcloud auth application-default login` (only the EDGAR parser owner needs this, and they use their own Google account — never share credentials).

#### TL;DR — what's automatic

- **Neon refreshes every weekday at 21:30 UTC** (≈ 06:30 KST next morning). Vercel Cron → Cloud Run worker → 7-step ingest. You'll see fresh OHLCV, news, features in the morning without doing anything.
- **EDGAR runs in the same job** but is mostly a no-op day-to-day (filings update quarterly). The first full-universe run populates ~300 filings; after that, only new accessions get pulled.
- **If you need data right now without waiting for cron**, you can trigger the same job manually with `curl -X POST https://tessera-ruby.vercel.app/api/cron/daily -H "Authorization: Bearer $CRON_SECRET"`. Takes ~7 min, runs in Cloud Run background. Don't do this more than a few times a day — every run hits the third-party APIs.

#### Step 0 — dev env setup (10 min, once)

```powershell
# 1. Clone (if you haven't) + pick up the latest
git pull

# 2. Fill in .env (one-time)
cp apps/worker/.env.example apps/worker/.env
# → open apps/worker/.env, paste values from the team KakaoTalk credential pin
# → DATABASE_URL is the most important one — that's what reads Neon
# → SEC_USER_AGENT: put your own contact email ("Tessera Pilot you@gmail.com")

# 3. Install
cd apps/worker
python -m venv .venv
.\.venv\Scripts\Activate.ps1            # Mac/Linux: source .venv/bin/activate
pip install -e .

# 4. Smoke test — should print "All checks passed"
python -m scripts.check_connections
```

#### Reading the data — 3 patterns (most → least common in Phase B)

**(a) Python from inside the worker package** — what Quant + LLM Pipeline code will look like:

```python
from sqlalchemy import text
from tessera_worker.db import session_scope

with session_scope() as session:
    # Latest features snapshot for one ticker
    row = session.execute(text("""
        SELECT ret_30d, ret_90d, vol_30d, rsi_14, sma_20, sma_50, volume_z
        FROM ticker_features
        WHERE ticker = :t
        ORDER BY ts DESC LIMIT 1
    """), {"t": "AAPL"}).first()
    print(dict(row._mapping))

    # Latest macro snapshot (yield curve + inflation expectations)
    macros = session.execute(text("""
        SELECT series_id, value FROM macro_series
        WHERE series_id = ANY(:ids)
          AND ts = (SELECT MAX(ts) FROM macro_series WHERE series_id='DGS10')
    """), {"ids": ["DGS2", "DGS10", "T10Y2Y", "T10YIE", "VIXCLS"]}).all()

    # Recent news for a ticker (last 7 days, title only)
    news = session.execute(text("""
        SELECT ts, source, title FROM news
        WHERE :t = ANY(tickers) AND ts >= NOW() - INTERVAL '7 days'
        ORDER BY ts DESC LIMIT 10
    """), {"t": "AAPL"}).all()

    # Latest 10-K excerpt for LLM context (first 8KB of management's prose)
    filing = session.execute(text("""
        SELECT filing_date, text_summary FROM filings
        WHERE ticker = :t AND filing_type = '10-K'
        ORDER BY filing_date DESC LIMIT 1
    """), {"t": "AAPL"}).first()
```

**(b) Raw SQL exploration** — useful for ad-hoc "what does the data look like" while writing features. Use Neon's web console at https://console.neon.tech or any Postgres client with `DATABASE_URL`. See `architecture.md` §6 "How to read the data we've stored" for a longer SQL cheatsheet.

**(c) Full filing text from GCS** — `filings.text_summary` is only the first 8KB. For the full document (e.g. to extract MD&A section), download from GCS:

```python
from google.cloud import storage
from urllib.parse import urlparse

uri = filing.raw_gcs_uri   # gs://tessera-raw/edgar/0000320193-26-000013.html
parsed = urlparse(uri)
blob = storage.Client().bucket(parsed.netloc).blob(parsed.path.lstrip("/"))
full_html = blob.download_as_bytes()
```

**Most of Phase B does NOT need this.** The 8KB `filings.text_summary` excerpt is enough for the standard persona prompt; only the EDGAR parser improvement task needs the full HTML. If you do need it:

1. Ping 정우 with your Google account email (not 정우's — your own).
2. 정우 grants you `roles/storage.objectViewer` on `gs://tessera-raw` from his terminal:
   ```powershell
   gcloud projects add-iam-policy-binding tessera-498200 `
     --member="user:<your-email>" --role="roles/storage.objectViewer" `
     --condition=None
   ```
3. On your own machine, run **once**:
   ```bash
   gcloud auth login                              # your own Google account
   gcloud auth application-default login          # again, your own account
   gcloud config set project tessera-498200
   ```
4. The `storage.Client()` snippet above works.

**Never share or log in with another teammate's Google account** — auth is per-person so audit trails stay clean.

#### Track-specific guidance

**Quant track (예슬, 준원) — build models on top of `ticker_features` + raw data**

What's in `ticker_features` today (already populated daily):
- Returns: `ret_1d`, `ret_5d`, `ret_30d`, `ret_90d`, `ret_1y`
- Volatility: `vol_30d`
- Momentum: `rsi_14`
- Trend: `sma_20`, `sma_50`
- Liquidity: `volume_z`
- Valuation / quality: `fcf_yield`, `peg`, `eps_cagr_3y`,
  `debt_to_equity`, `gross_margin`, `gross_margin_trend`,
  `market_cap_usd`, `operating_margin`

Pattern to follow for any next feature: add a pure function inside
`features/compute.py`, extend the fundamentals/macro loader if needed,
write through the same `ticker_features` upsert path, and pin behavior with
tests in `tests/test_features.py`.

For **risk gateway prep** (Phase C precursor): compute per-ticker volatility and correlation matrices using existing `ohlcv_1d`. Don't store yet — Phase C is when persona positions exist and we need to gate them.

**LLM Pipeline track (한솔) — assemble persona prompts**

Each persona's daily thesis needs 4 inputs from Neon (already populated):
1. **Feature snapshot** for the shortlisted tickers (~30 per persona) — `ticker_features` latest row per ticker
2. **Macro context** — last 30 days of relevant FRED series (Ray cares most; others get a summary)
3. **News** — last 24-48h headlines tagged to each ticker (`news` table, `:ticker = ANY(tickers)`)
4. **Filings excerpt** — `filings.text_summary` for the most recent 10-K/10-Q per ticker (Warren + Peter especially care about MD&A)

**Pattern to follow** (this is the `apps/worker/tessera_worker/agents/` directory you'll create):

```
agents/
  persona_loader.py      # parse personalities.md → in-memory dict
  prompt_assembler.py    # given (persona, ticker) → 6-part system prompt
  anthropic_runner.py    # typed call, Pydantic validation, retry on schema fail
  citation_validator.py  # verify cited_news_ids actually exist in news table
  models.py              # AnalystReport, Proposal Pydantic schemas
```

The **output** goes into the existing `analyst_reports` table:

```python
session.execute(text("""
    INSERT INTO analyst_reports
        (persona_id, ts, inputs_hash, parsed, raw_response, cost_usd)
    VALUES (:p, NOW(), :h, :parsed, :raw, :cost)
"""), {
    "p": "warren",
    "h": inputs_hash,           # SHA256 of the feature snapshot — for caching
    "parsed": parsed_json,       # validated AnalystReport.model_dump()
    "raw": raw_text,             # full Anthropic response for audit
    "cost": cost_usd,            # from anthropic SDK usage.input_tokens/output_tokens × pricing
})
```

The frontend swap (Phase B Week 3) reads from `analyst_reports` — so as soon as you start writing rows, the UI can pick them up.

**Cost guardrails (apply to both tracks)**

- Set `LLM_MAX_DAILY_COST_USD=5` in `.env` — the wrapper will refuse to call Anthropic if today's accumulated cost exceeds it.
- Use Haiku 4.5 for the universe screen step (cheap, fast); Sonnet 4.6 only for the deep thesis on shortlisted names.
- Cache the persona spec via `cache_control: ephemeral` on the system block — saves ~2K tokens × 4 personas × ~5 calls = 40K tokens/day repeated.

#### Worked examples — runnable demos in each track's folder

**⚡ Just want the paths? Here they are:**

| Track | Folder | Doc to read | Demo to run |
|---|---|---|---|
| **LLM Pipeline** (한솔) | `apps/worker/tessera_worker/agents/` | `LLM_pipeline_demo.md` | `python -m tessera_worker.agents.demo_warren_aapl` |
| **Quant** (예슬, 준원) | `apps/worker/tessera_worker/features/` | `Quant_demo.md` | `python -m tessera_worker.features.demo_fcf_yield` |
| **Anyone — "what's in the DB?"** | same `features/` folder | (no doc, just run it) | `python -m tessera_worker.features.demo_data_explorer` |
| **Anyone — "which macros drive which tickers?"** | same `features/` folder | (no doc) | `python -m tessera_worker.features.demo_macro_sensitivity` |

Both demos connect to Neon, run in ~5 seconds, print readable output, and are designed to be **forked** into your own feature/persona work. They live inside the package (not in `scripts/`) so `python -m tessera_worker.<...>.demo_*` works the moment `pip install -e .` is done — no extra setup.

> **Read this section once, then jump straight to your track's demo and markdown.** Each track owns its own folder; you do not need to touch the other track's files to be productive.

---

##### 🧠 If you're on **LLM Pipeline (한솔)** — start here

**Already done for you by 정우** (zero setup on your side):
- ✅ Anthropic API key is in Secret Manager (prod) and in the KakaoTalk pin (local). Don't generate a new one.
- ✅ Sentry is wired — your `raise`/`except` inside any agent module shows up in the `tessera-worker` Sentry project automatically.
- ✅ `personalities.md` is the canonical persona spec. CODEOWNERS lets all five team owners (정우, 윤채, 한솔, 예슬, 준원) approve changes — but big voice changes get a 카톡 heads-up first.
- ✅ `news`, `filings.text_summary`, `ticker_features`, `fundamentals`, `macro_series` tables are all populated overnight — you can read them right now.

**Your scope** (Week 2): build the `agents/` package that turns persona spec + Neon data → validated `analyst_reports` rows. Five new files, each small. Frontend wiring is Week 3.

**Your folder**: `apps/worker/tessera_worker/agents/`

```
agents/
  LLM_pipeline_demo.md       ← read first (5 min)
  demo_warren_aapl.py        ← run, then fork
  (later you'll add: persona_loader.py, prompt_assembler.py,
                     anthropic_runner.py, citation_validator.py, models.py)
```

**3-minute first run**:
```bash
cd apps/worker
.\.venv\Scripts\Activate.ps1
python -m tessera_worker.agents.demo_warren_aapl
```

You should see:
- All 6 prompt inputs Warren needs for AAPL (features, fundamentals, macro, news, 10-K excerpt) rendered as named XML-ish blocks
- The final assembled prompt at the bottom — **copy-paste into Anthropic console and you'll get Warren's first thesis**, no code needed

**Then read `LLM_pipeline_demo.md`** — it has 4 "Extend this" recipes (~10 lines each):
1. Swap personas (Warren → Cathie / Ray / Peter) without touching the data layer
2. Loop the universe (call `screen()` first, then iterate the shortlist)
3. Make a real Anthropic call (replace the print() with `client.messages.create(...)`)
4. Citation validation (every `[n_xxxxx]` Warren cites must resolve to a real news row)

**Your Week 2 task path** (recommended order):
- Day 1: run the demo + read the .md
- Day 2: fork `demo_warren_aapl.py` → `persona_loader.py` (parse `personalities.md` into a dict)
- Day 3: `prompt_assembler.py` — generalize the per-persona cuts into per-persona logic
- Day 4: `anthropic_runner.py` — real Anthropic call + Pydantic validation + cost log
- Day 5: `citation_validator.py` + first sanity-check thesis on AAPL (Warren writes a real one, you read it together)

**You will not need to touch**: `features/*`, `ingestors/*`, `risk/*`. Those are owned by Quant + Infra.

---

##### 📊 If you're on **Quant (예슬 + 준원)** — start here

**Already done for you by 정우** (zero setup on your side):
- ✅ All raw data is in Neon. `ohlcv_1d` (prices), `fundamentals` (FMP — three rows per period_end per ticker, one each for income / balance / cash_flow), `news`, `macro_series`, `filings` all populated overnight.
- ✅ `ticker_features` is the existing feature table, already populated daily with `ret_*`, `vol_30d`, `rsi_14`, `sma_{20,50}`, `volume_z`, and the latest valuation/quality features (`fcf_yield`, `peg`, `eps_cagr_3y`, `debt_to_equity`, `gross_margin`, `gross_margin_trend`, `market_cap_usd`, `operating_margin`). No parallel store.
- ✅ Property-test scaffolding exists in `tests/test_features.py` with 60 passing tests — copy the pattern when you add a new feature.
- ✅ Cron job auto-runs feature code plugged into `compute.py`'s `build()` — no extra deployment step beyond migration + worker deploy.

**Current Quant scope**: harden the shipped fundamentals features for Phase C — measure coverage/null rates, tighten market-cap precision edge cases, and wire these columns into the risk gateway/backtest selection rules. New features should still follow the same pattern: pure function + loader extension + migration + tests.

**Your folder**: `apps/worker/tessera_worker/features/`

```
features/
  compute.py                 ← existing production feature builder
  Quant_demo.md              ← read first (5 min)
  demo_fcf_yield.py          ← run, then fork
```

**3-minute first run**:
```bash
cd apps/worker
.\.venv\Scripts\Activate.ps1
python -m tessera_worker.features.demo_fcf_yield
```

You should see:
- ASCII bar chart of the equity universe ranked by FCF yield
- Mean, median, and Warren's screen list (tickers with FCF yield ≥ 6%)
- A `WRITE_BACK = False` flag at the bottom — that's the hook for when you wire this into `ticker_features` for real

**Then read `Quant_demo.md`** — it has 4 "Extend this" recipes (~5 lines each):
1. Sector overlay (group bars by GICS sector from `universe.py`)
2. Historical trend (5 years of fundamentals, not just snapshot — is FCF yield stable or trending?)
3. Wire into `ticker_features` for real (migration → `compute.py.build()` → property test → PR)
4. Property test the math (a `hypothesis` test that FCF / (close × shares) is finite)

**Your Week 2 task path** (recommended order — priority comes from Plan.md backlog):
- Day 1: run the demo + read the .md
- [x] Day 2: ship `fcf_yield` as a real `ticker_features` column — **shipped 2026-06-04** across 3 PRs that progressively tightened precision. Final state: `compute_fcf_yield()` in `features/compute.py` returns rolling-TTM FCF / fresh USD market cap, with multi-candidate cross-validation. Specifically:
    - **TTM rollup** decomposes FMP's cumulative-YTD shape into a true 12-month value via `TTM = last_FY + current_YTD − prior_FY_YTD_at_same_period`. Falls back to `max(window)` (last full FY) when period anchors are missing.
    - **Currency conversion** via `FX_TO_USD` for non-USD reporters (TWD, EUR, GBP, JPY, KRW, HKD, CNY, CAD). Unknown currency → drop.
    - **Market cap** estimated via `cross_validated()` over 4 candidates (close×diluted, close×basic, payload-mcap-cash, payload-mcap-income). Disagreement → `max` (conservative-for-yield).
    - **Safety**: ±100% sanity bound + `build(*, with_fundamentals: bool = True)` flexibility toggle (default daily, no API cost; toggle exists so future cadence splits flip from the orchestrator without touching compute logic).
    - **Live verification (31/42 tickers write)**: AAPL 2.83%, COST 2.06%, META 3.38%, TSM 1.51% — all within ±10% of independently-computed real values. Ranking is Warren-correct: XOM/MA/JNJ at top, mega-cap tech mid, cash-burning growth at bottom.
    - **50 tests**. Includes worked-example tests for AAPL Q2 FY26 and COST Q3 FY26 TTM math.
    - **Deferred to Phase C** (data quality work): UNH/NVDA/AMZN/COIN edge cases (sparse FY anchors, alternating null filings, one-time spikes). Sanity bound keeps these from polluting the LLM prompt; precision fix waits for a dedicated daily mcap source (FMP `key_metrics`) and FY-aware ingestion.
- [x] Day 3 / Phase C precursor: `peg` — shipped 2026-06-06 as a trailing
  PEG proxy (`P/E ÷ EPS CAGR %`). True forward PEG still needs an analyst
  estimates source.
- [x] Day 4 / Phase C precursor: `eps_cagr_3y` — shipped 2026-06-06 from
  annual income rows with positive-EPS guards.
- [x] Day 5 / Phase C precursor: `debt_to_equity`, `gross_margin`,
  `gross_margin_trend`, `market_cap_usd`, `operating_margin` — shipped
  2026-06-06. Correlation matrix / sector exposure remains Phase C
  risk-gateway scope.

**You will not need to touch**: `agents/*`, `ingestors/*` (mostly), `risk/*`. Those are owned by LLM Pipeline + Infra.

---

##### 🤝 Where the two tracks meet

The two tracks share **one boundary**: `ticker_features`. Quant writes new columns into it; LLM Pipeline reads from it.

```
                                         writes
  Quant (features/compute.py)  ──────────────────►  ticker_features
                                                          │
                                                          │ reads
                                                          ▼
  LLM Pipeline (agents/prompt_assembler.py)  ──►  Warren's <features> block
```

So when Quant ships `fcf_yield` into `ticker_features`, the next cron run automatically lights it up for every persona's prompt. **No coordination needed** beyond the column existing on Day 5 vs Day 3 — agree on column names in advance and you're done.

The same is true for `filings.text_summary` (SEC EDGAR ingestor writes it, LLM Pipeline reads it for the `<filing>` block) and `news` (ditto for `<news>`).

---

##### Real-data quirks the demos surface (good "first issue" material)

Both demos hit real production data and surface its imperfections — these are natural starting points for first PRs:

| Quirk | Owner | Where it shows up |
|---|---|---|
| NewsAPI tags ~30% of AAPL stories with false positives (Disney World, NBA Finals, …) | Quant or LLM Pipeline | LLM demo's `<news>` block is dominated by noise |
| SEC 10-K primary doc is XBRL-tagged; current 8KB excerpt is metadata header, not the MD&A prose Warren wants | LLM Pipeline | LLM demo's `<filing>` block shows XBRL goo instead of prose |
| ~~TSM FCF yield 48% — ADR share-count units mismatch~~ — **fixed 2026-06-04** in the Week 2 Quant `fcf_yield` ship. Root cause turned out to be currency (TWD vs USD), not ADR ratios. See `compute_fcf_yield()` + `FX_TO_USD`. TSM now reads 1.51%. | Quant | (closed) |
| **fcf_yield precision edge cases** — UNH (5.7% vs real ~3%), NVDA (0.07%), AMZN (0.35%), COIN (14.7%) read off-band when fundamentals data is sparse (few FY anchors, alternating null filings, or one-time spikes). Sanity bound prevents pollution of the LLM prompt. Proper fix needs a dedicated daily mcap source (FMP `key_metrics`) and FY-aware ingestion. | Quant (Phase C) | `ticker_features` rows for these names sit at the boundary or are dropped |

Pick one as your first PR. They're all real, small, and improve the downstream signal quality for everyone.

#### When something looks wrong

- **Cloud Run cron run failed?** Check `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=tessera-worker AND severity>=ERROR" --freshness=1d`. Anything user-visible should also surface in Sentry → `tessera-worker` project.
- **DB has stale data?** Check the latest `fetched_at` on the suspected table (`SELECT MAX(fetched_at) FROM news`). If older than 24h, the cron skipped or failed.
- **API rate-limited mid-run?** All ingestors are idempotent — just trigger again. `ON CONFLICT DO UPDATE` handles duplicates.

### Week 2 — Persona runner + full desk
- [x] **Persona loader** (한솔, PR #29 + #30 fix-forward, shipped 2026-06-02): `apps/worker/tessera_worker/agents/persona_loader.py` — parses the 4 `## <Name> — Operational system prompt` sections from `personalities.md`, returns a `{persona_id: spec_text}` dict, cached via `lru_cache`. Path resolution walks up from the package to find `personalities.md` at repo root. Strict validation (raises if any persona is missing). 5 pytest tests passing.
- [x] **Prompt assembler** (한솔, PR #33, shipped 2026-06-02): persona spec + feature snapshot + memory recall → prompt. `apps/worker/tessera_worker/agents/prompt_assembler.py`. Ray branch added Week 2 followups for RegimeReport JSON shape
- [x] **Pydantic models** (PR #33, shipped 2026-06-02): `AnalystReport`, `Proposal` with full field validation in `packages/shared/tessera_shared/schemas.py`. `RegimeReport` + `RegimeAllocation` added 2026-06-03 for Ray (parallel schema, same table, `persona_id='ray'` discriminator)
- [x] **Anthropic SDK wrapper** (PR #33, shipped 2026-06-02): typed call, 2-attempt retry with feedback on schema/JSON failure, tokens + cost logged per call to `llm_call_log`. `_normalize_conviction()` coerces LLM mistakes (percent, 1-10 scale, words) — 11 parametrized tests
- [x] **Citation validator** (PR #33, shipped 2026-06-02): `apps/worker/tessera_worker/agents/citation_validator.py`. Runner drops invalid `n_xxxxxxxx` IDs before persist; report fails if any cite lacks a `news` row
- [ ] **Universe screen** (Haiku 4.5): per persona, narrow ~500 → top 30 — **deferred to Week 4+**: current universe is ~50 names, no funnel needed. Revisit when universe > 200
- [ ] **Hybrid selection**: ∪ with mechanical primary-metric top-30 per persona — see risk: *Haiku false negatives* — **blocked on Haiku screen**
- [ ] **Screen audit job** (weekly): Sonnet re-evaluates 10 randomly-sampled rejected names; alert if any score ≥ inclusion threshold — **blocked on Haiku screen**
- [ ] **`screen_promotion_rate` dashboard**: target band 30–80% — **blocked on Haiku screen**
- [x] **Deep thesis** (Sonnet 4.6, PR #33, shipped 2026-06-02): currently runs on hand-picked tickers via CLI / `persona_batch.py`. "shortlist only" gating pending Haiku screen
- [x] **Prompt caching** (PR #33, shipped 2026-06-02): persona spec marked `cache_control: ephemeral` in `anthropic_runner.py:258`. Verified cache hits in `llm_call_log` cost reduction
- [x] **pgvector recall** — **shipped 2026-06-05** (PR #42 + follow-ups). Voyage AI embeddings (1024-dim `voyage-3.5-lite`, Anthropic-recommended, ~$0.0003/mo at pilot scale, free-tier covers indefinitely). New `agents/embeddings.py` (`embed_thesis`/`embed_query`/`to_pgvector_literal`). `persist_analyst_report` writes one `persona_memory` row per proposal as best-effort (NULL embedding if Voyage unavailable; persistence never blocks). `fetch_memory_recall` picks strategy at runtime: similarity (`<=>` cosine, query built from top-3 news titles + key features) when Voyage works, else recency fallback — both paths upper-bounded by `as_of` for backtest correctness. Recall lines tagged `sim=0.234` or `recency` for prompt audits. Migration `002_persona_memory_vector_1024.sql` (VECTOR 1536→1024, ivfflat WHERE embedding IS NOT NULL). 4 new tests.
- [x] **Cost logging** (PR #33, shipped 2026-06-02): every call → **`llm_call_log` table** `(persona_id, stage, model, tokens_in, tokens_out, cost_usd, latency_ms, ts)`. Daily cap check in `_check_daily_budget()`. ~~Grafana metric~~ deferred to Phase C observability
- [x] **First sanity check** — shipped 2026-06-03. Warren wrote real theses on AAPL (3 runs, all `side=hold conv=0.55-0.62 cash=0.12-0.15`, ~$0.02 each), Cathie on NVDA (tri-scenario thesis, conv=0.72), Peter on COST (hold, conv=0.62). Ray's `instrument`+ETF schema doesn't fit `Proposal` — needs separate `RegimeProbabilities` path, deferred to Week 3.

#### Carried over from Phase A — 정우 owned these (offloaded from the LLM and Quant tracks for Week 2)
- [x] **Sentry DSN registration** on web + worker — shipped 2026-06-01. Both `tessera-web` + `tessera-worker` projects live, errors-only (no perf traces / replays) for free-tier cost guard. End-to-end verified via `/api/sentry-verify` (now removed). Pattern: explicit `Sentry.captureException` + `flush()` in Next 14 route handlers (auto-instrumentation isn't reliable there).
- [x] **GCP project + Cloud Run + Cloud Tasks + Secret Manager** — shipped 2026-06-01. Project `tessera-498200` (us-east1), Artifact Registry repo `tessera`, service account `tessera-worker` with `roles/secretmanager.secretAccessor`, 9 secrets in Secret Manager. Worker container at `tessera-worker-ffr7g3a76a-ue.a.run.app`. Vercel Cron now triggers Cloud Run via `WORKER_WEBHOOK_URL` and the full 6-step ingest runs autonomously — verified Neon row counts incremented end-to-end. Implementation notes captured in `docs/adr/006-vercel-cloud-run-split.md`.
- [x] **SEC EDGAR filings ingestor** — shipped 2026-06-01. New 7th step in daily orchestrator. Per ticker: 2 × 10-K + 4 × 10-Q (≈1.5 yrs of management prose). Body excerpt (8KB) into `filings.text_summary`, raw HTML to GCS `tessera-raw/edgar/{accession}.html`. Skip-if-already-have on accession means daily runs are no-ops once steady-state. Smoke-test verified end-to-end with AAPL + MSFT (12 filings, 49 MB HTML, 32s local run). Full universe run scheduled with next Cloud Run cron. Frees 예슬 to focus on features + risk gateway prep for Phase C.

### Week 3 — Chat + backtest + hardening
- [x] **Persona batch job** (LLM Pipeline) — **shipped 2026-06-05**. `apps/worker/tessera_worker/jobs/persona_batch.py` loops 4 personas (Warren/Cathie/Peter shortlists of 10 tickers each + Ray single regime call = 31 cells) and calls `anthropic_runner.run_thesis()` / `run_regime_thesis()`. Per-cell errors counted, never raised; `LlmDailyBudgetExceeded` + `LlmDisabledError` halt the run cleanly. Honors both `LLM_MAX_DAILY_COST_USD` (system cap) and `--max-cost` (per-run cap, default $5). HTTP endpoint `/jobs/persona-batch` on the worker (replaces the prior TODO stub) runs in `BackgroundTasks` and chains the **hallucination_canary** afterward — canary violations page Sentry but don't roll back the batch. Vercel cron `cron/weekly` schedule `0 22 * * 5` (Fri 22:00 UTC ≈ 17:00 ET, 30 min after the daily ingest finishes at 21:30 UTC) hits the new endpoint. CLI: `python -m tessera_worker.jobs.persona_batch [--personas …] [--dry-run] [--max-cost N] [--as-of YYYY-MM-DD]`. Expected per-run cost: ~$1.35 (10 tickers × 3 personas × ~$0.04 incl retry + Ray $0.05) → ~$5–7/mo at weekly cadence. 9 unit tests + live dry-run (31/31 cells PASS, $0).
  - **This unblocks `FEATURE_REAL_LLM=true` on prod.** Until this commit, the flag was set but no cron was calling `anthropic_runner` — only manual CLI. From the next Friday cron tick, real theses land in `analyst_reports` weekly without operator action.
- [x] **Ray RegimeProbabilities runner** (LLM Pipeline) — **shipped 2026-06-03** (`fix/week2-followups` branch). Parallel `RegimeReport` schema (asset-class ETF allocations, `instrument`-keyed, per-slice cap 0.40 vs. Proposal's 0.20) + `RegimeProbabilities` (goldilocks / reflation / stagflation / deflation, sums to 1.0). `run_regime_thesis()` in `agents/anthropic_runner.py` mirrors the stock-picker retry path. **Persistence**: discriminated union into existing `analyst_reports` table — `persona_id='ray'` row carries the RegimeReport shape in `parsed` JSONB; UI / risk-gateway / leaderboard read on `persona_id` and branch on the schema. (Separate `regime_reports` table was the alternative; chose discriminator to keep one source of truth for "what did the desk say today" queries.) CLI: `python -m tessera_worker.agents.anthropic_runner ray` (no ticker arg). 2 tests pin the allocations-validate + weights-sum behavior. Live run 2026-06-03: probabilities 28/35/22/15, 8 ETF allocations including VTI/VXUS/DBC/GLD/TIP/IEF/TLT/QQQ, cash_target 0.08, $0.025/run.
- [x] **Chat backend** — **shipped 2026-06-05** (backend only — frontend `analyst-chat.tsx` SSE consumer is the Frontend track's next slice).
  - **Worker** `apps/worker/tessera_worker/agents/chat.py` — `run_chat_stream(persona, message, history)` async generator + 6-part system assembler:
    1. Universal chat policies (compliance, no personalized advice, identity, hallucination guard)
    2. Persona operational spec (investing philosophy)
    3. Persona chat fine-tuning spec (response shape, vocabulary, signature + forbidden phrases)
    4. Recent reports (last 5 `analyst_reports` for this persona — what they've actually written)
    5. Ticker features (RAG via `ticker_resolver` Levels 1-6 — Korean aliases, typos, Haiku roundabout)
    6. Conversation history + user message (via messages array, not system block — keeps prompt cache hot)
  - **persona_loader** extended: `load_chat_specs()`, `load_universal_chat_policies()` parse the `# Chat fine-tuning specifications` half of personalities.md.
  - **FastAPI endpoint** `POST /api/chat/{persona_id}` returns `text/event-stream`. Each delta is `data: <text>\n\n`; ends with `data: [DONE]`. Bearer-auth via `WORKER_WEBHOOK_SECRET`.
  - **Next.js proxy** `apps/web/app/api/chat/[personaId]/route.ts` — Edge runtime, pipes the worker's SSE through unchanged. Browser → Vercel → Cloud Run, single-origin, no CORS.
  - **Hard safeguards reused**: `check_daily_budget()` blocks chat when daily cap hit; `FEATURE_REAL_LLM` gates the call; chat calls log to `llm_call_log` with `stage='chat'` so daily-cost dashboard aggregates correctly.
  - **Live smoke test** (Warren × AAPL): "Apple is a business I understand and admire... at a 2.83% free cash flow yield, I am being asked to pay handsomely for a business that grows in the mid-single digits. That math does not clear my 6% hurdle..." — voice perfect, ticker auto-resolved + DB fcf_yield cited correctly, $0.003 / 6.5s with cache hit on system block.
  - **11 unit tests + 163/163 worker total**. Streaming itself smoke-tested via direct async call (not unit-mockable cleanly).
  - **Not in this PR** (Phase D scope): `chat_messages` table for cross-session history, per-user auth (Firebase), pgvector chat memory, post-hoc canary on chat output.
- [x] **Backtest harness** (LLM Pipeline) — **shipped 2026-06-04**, **acceptance verified 2026-06-05**. `apps/worker/tessera_worker/jobs/backtest_harness.py` — replays N trading days × M personas × K tickers with point-in-time correctness. All `fetch_inputs` queries upper-bound on `as_of` (features / news / fundamentals / filings / macros / persona_memory) so no future data leaks into the prompt. New `backtest_reports` table (separate from `analyst_reports` to keep UI / risk gateway clean) plus a per-run `run_id`. CLI flags: `--days`, `--personas`, `--tickers`, `--dry-run` (skips LLM, verifies assembly path), `--max-cost` (defaults $5). Honors `LLM_MAX_DAILY_COST_USD` on top of `--max-cost`. Same 2-attempt retry-with-feedback path as production. Followups (PRs #41–#42 + descendants):
    - 2-attempt retry + persist-unparseable (parsed=NULL row preserves raw text + reject reason for hand-review).
    - `JSONDecoder.raw_decode()` parser ignores trailing chatter (Cathie scenario narration ~5% of cells).
    - Targeted retry guidance — `_retry_guidance_for()` pattern-matches the error (JSONDecode / what_would_make_me_wrong / conviction-missing / cited_news_ids) and gives the model a specific corrective instruction instead of generic "Fix JSON only".
    - `personalities.md` field-name drift fix (`confidence` → `conviction`) + defensive alias in `_normalize_conviction` so 100%-silent signal-loss regressions can't recur.
    - `what_would_make_me_wrong` cap 5 → 8 (Cathie's scenario-structured voice routinely enumerates 6–7 risks).
    - **Live run (60 cells, 10 days × 3 personas × 5 tickers)**: 1.67% schema fail (target <2%, PASS), $4.63 cost. Smaller 18-cell follow-up after the conviction + parser fixes: 0% schema fail, $0.65, conviction distribution diverse and persona-appropriate (Cathie 0.38–0.82, Warren 0.55–0.62, Peter 0.45–0.72), voice differentiation strong (Warren simple metaphors / Cathie Base-Bull-Bear scenarios / Peter store-walker anecdotes).
- [→] **Hard rule enforcement** — **moved to Phase C Week 4 Risk Gateway** (2026-06-05). Same per-persona validators (Warren `target_weight > 0.18` reject, etc.) belong in `risk/gateway.py` where the trade-time check happens. Implementing twice would diverge. Schema-level global `target_weight ≤ 0.20` cap already in place.
- [x] **Hallucination canary** — **shipped 2026-06-05**. `apps/worker/tessera_worker/jobs/hallucination_canary.py` — invariant checks on the most-recent batch's outputs (dropped probe-prompt approach in favor of post-hoc invariants, which test actual production behavior). Five checks:
    1. Every `cited_news_ids` resolves to a real `news` row.
    2. No `target_weight ≥ 0.19` (mode-collapse signal vs the 0.20 schema cap — Plan §11 risk).
    3. `side ∈ {buy, add}` requires `conviction ≥ persona floor` (Warren 0.55, Cathie/Peter 0.50).
    4. `thesis_md` contains no compliance-forbidden phrases (`guaranteed return`, `can't lose`, `risk-free`, `insider tip`, etc.).
    5. Warren/Peter `thesis_md` mentions no derivatives (`covered call`, `leveraged`, `margin loan` — spec drift).
  - CLI: `python -m tessera_worker.jobs.hallucination_canary --latest` (default = most-recent backtest run), `--run-id <uuid>`, or `--table analyst_reports --since YYYY-MM-DD` for prod-batch mode.
  - Exit 0 = pass, 1 = fail (Sentry capture on failure). Weekly cron should run canary as the LAST step after `persona_batch.py` and treat exit 1 as stop-the-world (skip next batch + page on-call).
  - First live run against the 18-cell backtest: **0 violations, PASS**. 23 unit tests cover each check independently + the result/threshold sanity.
- [→] **Cost cap** — **functional component shipped 2026-06-02** (`check_daily_budget()` hard-pauses on cap breach; cost logged per call to `llm_call_log`). Grafana visualization + Slack alerts moved to Phase C Week 4 observability work (rolled forward; same data source, just unwired alerts).
- [x] **Frontend swap — thesis half** (Frontend track) — **shipped 2026-06-05**. `lib/mock/reports.ts` + `lib/mock/proposals.ts` deleted; `/api/reports/[personaId]` + `/api/proposals/[personaId]` Edge proxies pipe Cloud Run worker endpoints (`GET /api/reports/{persona}` + `GET /api/proposals/{persona}` in `main.py`) into the persona detail sheet + `/proposals` page. Worker reshapes `analyst_reports.parsed` — AnalystReport for stock-pickers, RegimeReport for Ray — into a uniform `{positions, cashWeight, regime?, asOf}` shape so the UI consumes both schemas without branching. Types in `lib/thesis-types.ts`; client fetcher with AbortController + skeleton + empty states in `lib/analyst-data.ts`. Edge cache 60s s-maxage matches the weekly cron cadence. Live verified — Warren MCO/JNJ from yesterday's batch + Ray's 8 ETF regime allocations render correctly.
- [→] **Frontend swap — performance + portfolio half** — **deferred to Phase C Week 5**, blocked on the paper-trading engine populating `persona_performance` + `persona_portfolios`. Showing mock until then is more honest than synthesizing fake P&L. `lib/mock/performance.ts` + `lib/mock/portfolio.ts` intentionally retained.

**Compression note**: previously three weeks (runner / desk / chat). Now two
weeks. Risk: backtest review is rushed. Mitigation: review sample size from 10
to 5 per persona; defer voice tuning to post-launch iteration.

### Acceptance criteria (as of 2026-06-05)
- 🟢 Open Warren in UI → see real thesis written today, with citations linking to real news rows
  - **shipped 2026-06-05** — `/api/reports/[personaId]` + `/api/proposals/[personaId]` Edge proxies pipe Cloud Run worker responses (`GET /api/reports/{persona}` + `GET /api/proposals/{persona}` in `main.py`) into the persona detail sheet + `/proposals` page. Worker reshapes `analyst_reports.parsed` (AnalystReport for stock-pickers, RegimeReport for Ray) into a uniform `{positions, cashWeight, regime?, asOf}` shape so the UI consumes both schemas without branching. Mock `lib/mock/reports.ts` + `lib/mock/proposals.ts` deleted; types extracted to `lib/thesis-types.ts`; client-side fetcher with AbortController + skeleton + empty states in `lib/analyst-data.ts`. Edge cache 60s s-maxage matches the weekly cron cadence. `lib/mock/performance.ts` + `lib/mock/portfolio.ts` intentionally left in place — `persona_performance` table is populated by the paper-trading engine (Phase C Week 4), so showing mock until then is more honest than synthesizing fake P&L.
- 🟢 Open chat with Cathie → real Sonnet response, in her voice
  - **Backend ✅ shipped 2026-06-05** (`/api/chat/[personaId]` SSE on worker + Edge proxy on Vercel). Voice + ticker-aware RAG live; smoke-tested Warren × AAPL with correct fcf_yield citation.
  - **Frontend ✅ shipped 2026-06-05** — `analyst-chat.tsx` SSE consumer via fetch + ReadableStream (EventSource is GET-only). `lib/chat-stream.ts` async generator handles SSE framing + error/abort. `lib/chat-starters.ts` keeps greeting + suggested prompts out of `lib/mock/`. `lib/mock/chat.ts` deleted. AbortController cancels in-flight stream on persona switch / unmount. Footer text updated from "mock-generated" to "Powered by Sonnet 4.6 · not financial advice". Next build clean, all 8 routes pass typecheck.
- 🟢 Cost dashboard shows < $5/day on average
  - Every call logged to `llm_call_log` with cost. Live backtest (60 cells) ran $4.63. Daily cap (`LLM_MAX_DAILY_COST_USD`) enforced in `_check_daily_budget()`. Grafana export deferred to Phase C.
- 🟢 Backtest of 30 days × 4 personas shows < 2% schema-validation failure rate
  - Verified at 10 days × 3 personas × 5 tickers (60 cells): **1.67%** fail rate, PASS.
  - 4 personas (incl. Ray): Ray uses parallel `RegimeReport` schema, will need a separate Ray-aware backtest cell type. Carried into Phase C precursor work.
  - 30-day expansion: gated on Anthropic credit budget; current 10-day proxy passed the underlying gate.
- 🟢 0 hallucinated tickers reached the (would-be) UI in backtest
  - `citation_validator` rejected 0 cells on bad news IDs across the 60-cell run. `assemble_prompt` only emits tickers from `tessera_worker.universe` so the schema cannot produce a non-universe `ticker`.

### Open decisions to resolve here
- ~~**Chat model**: Sonnet 4.6 always vs. fine-tuned Haiku per persona~~ — **Decided 2026-06-05: Sonnet 4.6 always.** Live chat backend shipped on Sonnet; voice quality + cost both acceptable (~$0.003/msg with system-block caching). Revisit if chat volume crosses 500 msg/day per persona.

### 🏁 Phase B END — 2026-06-05

All five §4 acceptance criteria 🟢:
- 🟢 Open Warren in UI → real thesis with citations
- 🟢 Open chat with Cathie → real Sonnet response in voice
- 🟢 Cost < $5/day average (live: ~$1.35/weekly run = $5-7/mo)
- 🟢 Backtest < 2% schema-fail (60-cell: 1.67%, 18-cell follow: 0%)
- 🟢 0 hallucinated tickers reached UI (canary 0 violations across 18 rows)

**Deferred to Phase C** with documented rationale:
- Hard rule per-persona caps → merged into Risk Gateway (single home, single code path)
- Cost-cap Grafana viz → joins observability work in Phase C Week 4 (functional hard-pause already shipped)
- Quant feature consumption/hardening → wire shipped quality features into risk-gated backtests; add coverage/null-rate telemetry
- Performance + portfolio frontend swap → blocked on Phase C paper engine populating `persona_performance`
- fcf_yield precision edge cases (UNH/NVDA/AMZN/COIN) → needs dedicated daily mcap source (Phase C ingest plane work)

### Lessons from Phase B (written 2026-06-12, with Phase-C hindsight)

Same convention as "Lessons from Phase A" in §3 — the expensive ones,
kept inline here so they're in view when the next phase gets planned:

1. **Silent signal loss is the worst failure mode.** A field rename in
   personalities.md (`confidence` → `conviction`) zeroed a signal with no
   error anywhere. Every LLM-output field needs a consumer-side existence
   check or a canary — and the canary should exist BEFORE the first prod
   batch, not after.
2. **LLMs decorate JSON.** ~5% of Cathie's cells appended narrative after
   the closing brace. `JSONDecoder.raw_decode` (parse the first object,
   log the rest) beat prompt-nagging.
3. **Retry feedback must be specific.** Generic "fix your JSON" wasted
   the retry; pattern-matching the validation error into a targeted
   instruction (`_retry_guidance_for`) made attempt 2 actually converge.
4. **Single-source fundamentals fail per-ticker, not globally.** Visa
   broke FMP and XBRL differently than NVDA did → became Phase C's
   3-tier fall-through with per-field newest-non-null walking.
5. **Per-cell sizing can't produce a coherent book.** Warren's 8% BRK.B
   + nine 0% rows + "12% cash" = 20% total exposed the structural flaw →
   the v2 two-pass redesign (research per ticker, ONE construction call,
   deterministic `normalize_book`).
6. **Server-authoritative fields must be force-set, never `setdefault`.**
   Ray's Sonnet volunteered its own `as_of` and won the tie for weeks —
   every Ray row carried a 17-month-old book date until the paper
   engine's first run surfaced it (#98).
7. **Acceptance tests should name the exact log line and where it
   appears.** "Verify Voyage via chat" was unverifiable — recall's
   `sim=` tag only ever fires in the weekly batch (#102).

---

## 5. Phase C — Paper execution + attribution (Weeks 4–5)

**Goal**: Each persona's portfolio executes in paper. Daily P&L tracked. Leaderboard shows real Sharpe/MDD.

### Week 4 — Risk gateway + paper engine + mark-to-market
- [x] **Risk gateway — thin-validator core shipped 2026-06-11** (`apps/worker/tessera_worker/risk/gateway.py`). Pure Python `gate(report) → RiskCheckResult`, wired into `construct_portfolio`'s retry loop so a rejection becomes specific feedback to the construction LLM on attempt 0. 7 unit tests. Per-check status:
    - [x] **Ticker exists** in `universe.py` — final anti-hallucination stop on the persistence path
    - [x] **Per-persona single-name cap** from `persona_constraints.PERSONA_CONSTRAINTS` (re-check; `normalize_book` enforces it deterministically first). **Subsumes Phase B's deferred "Hard rule enforcement" task — single home, single code path.**
    - [x] **Sector cap** — was prompt-only until now (`normalize_book` can't see sectors); sector from `universe.META_BY_TICKER`
    - [x] **Conservation of NAV** — sum=1.0 re-check (under-allocation side; schema only rejects >1.0)
    - [x] **Parametric VaR** at 99% — **shipped 2026-06-12 (#105)**. `risk/var.py`: delta-normal VaR99 over calendar-INTERSECTED daily log returns (crypto+equity books need one clock), ≥60 obs required ("can't measure" never rejects). Per-persona caps in `persona_constraints`, calibrated against books measured that day with ~2× headroom (warren 3.5% / cathie 8.5% / peter 4.5% / ray 2.5%).
    - [x] **Drawdown floor** — **shipped 2026-06-12 (#105)**. LIVE-track drawdown only (hypothetical backfill is a chart artifact, not risk history); beyond the persona floor (20/35/25/15%) the gate refuses auto-execution → operator review.
    - [x] **Ray regime-allocation gate** — **shipped 2026-06-12 (#105)**. `gate_regime()` in `run_regime_thesis`'s retry loop: instrument universe membership, sum=1.0, slice-cap re-check, VaR/DD. First live smoke also caught warren/cathie's pre-#94 books violating SECTOR caps — the Friday batch re-shapes them via retry feedback, by design.
- [x] **PaperEngine — v1 shipped 2026-06-12** (`risk/paper_engine.py`, flag-gated `FEATURE_PAPER_EXECUTION`, default off). Diff latest unexecuted book (tracked by `report_id` on trades) vs current positions → fill at each ticker's next bar OPEN (Friday book → Monday open, per the original rule). Fractional shares, no commissions/slippage in v1. $100K paper bootstrap per persona. NAV conservation exact by construction (unit-pinned). Ray's `allocations` execute through the same path as `proposals`.
- [x] **Order ledger** — `persona_trades` rows carry report_id + rationale per fill; `persona_portfolios` daily snapshots (idempotent upsert keyed on calendar day) are the positions trail. No separate pending-orders table: order creation and fill happen in the same daily step by design.
- [x] ~~LISTEN/NOTIFY~~ — **dropped, simpler design won**: the engine runs as the 14th `ingest_daily` step. A daily-batch desk doesn't need event push; the next ingest IS the rebalance evaluation.
- [x] **EOD mark-to-market** — same step: values at latest bar CLOSE, recomputes `persona_portfolios.total_value` daily even when no rebalance fired.
- [x] **Persona performance writer** — same step: pnl_day/pnl_cum/return_day/return_cum vs $100K start, sharpe_30d (needs ≥5 obs), mdd_30d, trades_count. hit_rate deferred (needs closed-lot tracking).
- [x] **Flip `FEATURE_PAPER_EXECUTION=true`** — flipped in `deploy_cloud_run.ps1` 2026-06-12 (PR #96; the same deploy ships the #94 gateway + #95 engine code). First flagged nightly run bootstraps 4 × $100K paper portfolios and executes each persona's latest book at the next bar open — verify `persona_trades` / `persona_portfolios` / `persona_performance` row counts after.
- [x] **Cost observability — Grafana dashboard LIVE 2026-06-12** (operator setup per `docs/runbooks/observability-grafana-voyage.md`: read-only `grafana_ro` role + datasource + `docs/grafana/llm-cost-dashboard.json` import — 7 panels over `llm_call_log`). Remaining optional: alert rules at $5/$10/$20 (email/Slack contact point). Original scope: (rolled forward from Phase B Week 2 plan). Source data already populated in `llm_call_log`; this is dashboard + webhook wiring. Alert thresholds: $5/day (info), $10/day (warning), $20/day (page). The hard pause (`check_daily_budget`) stays as the safety net — alerts give earlier warning.
- [x] **Quant fundamentals features — PEG / EPS CAGR 3y / debt-to-equity / gross margin trend** — shipped locally 2026-06-06. `004_quality_features.sql` adds any missing columns idempotently; `features/compute.py` computes the values from existing Neon `fundamentals` + latest `ohlcv_1d` close; prompt assembly and chat now read the columns. Remaining Phase C work is **consumption + hardening**: wire these into the risk gateway/backtest selection rules, add dashboards for coverage/null rates, and tighten known market-cap precision edge cases with a dedicated daily FMP `key_metrics` source.
- [x] **Data resilience layer — 3-tier fundamentals fall-through + cross-validation** — shipped 2026-06-09. Phase B's single-source assumption broke on Visa: FMP returned mostly-null preliminary rows for the latest filing, EDGAR's `WeightedAverageNumberOfShares*` concept isn't tagged by V (and `EntityCommonStockSharesOutstanding` stopped being filed after 2010), `GrossProfit` isn't reported at all. Fix is a layered pattern, see architecture.md §6 "Data resilience":
  - **Loader walks rows newest-first per field** instead of locking the latest row — partial filings can be rescued by older non-null observations (`features/compute.py::_load_fundamentals_latest`). Same pattern applied to balance.
  - **EDGAR ingestor** (`ingestors/sec_edgar_facts.py`) gains a capex concept-priority list (`PaymentsToAcquirePropertyPlantAndEquipment` → `PaymentsToAcquireProductiveAssets` → `PaymentsForCapitalImprovements`) and walks `dei.EntityCommonStockSharesOutstanding` as a shares fallback after the us-gaap loop.
  - **New yfinance ingestor** (`ingestors/yf_shares.py`) pulls `sharesOutstanding` / `marketCap` / `trailingPegRatio` / `grossMargins` / `trailingPE` / `forwardPE` from `yf.Ticker(t).info`, normalizes ticker (V → V, BRK.B → BRK-B), writes a single synthetic `(ticker, today, income)` row tagged `source='yfinance'`. `compute.build()` consults these **only when the EDGAR-derived path returns None**, bounded by the same sanity envelope (PEG ≤ 100, margins ∈ [-1, 1], P/E ≤ 500). Wired as a daily orchestrator step after `edgar_facts`.
  - **`005_pe_ratios.sql`** adds `pe_trailing` + `pe_forward` columns; UI renders P/E (TTM) as the 6th Quality cell. **V verification after backfill**: fcf_yield 3.94%, market_cap $537B, PEG 1.40, gross_margin 97.78%, P/E 31.0 — vs all-null pre-fix. Remaining N/As (`eps_cagr_3y`, `gross_margin_trend`) require a historical EPS / margin series, tracked as a follow-up below.
  - **Cross-validation framework** (`compute.py::cross_validated`) generalizes the disagreement-detection / conservative-pick pattern already in `estimate_market_cap`. Today only mcap consumes it; next step is wiring debt_to_equity / gross_margin / FCF to consult more than one source and log disagreements.
  - **Debug helpers shipped alongside**: `scripts/inspect_ticker_features.py`, `scripts/inspect_v_rows.py`, `scripts/dump_v_xbrl_concepts.py`, `scripts/dump_v_dei.py` — diagnostic playbook for the next "why is ticker X blank?" incident.
- [x] **Historical EPS / margin trend ingestor + income loader cap fix** — shipped 2026-06-09 as `ingestors/yf_history.py` plus a fix in `_load_fundamentals_latest`. Two pieces:
  1. **yf_history**: calls `yf.Ticker(t).income_stmt`, extracts diluted EPS + revenue + grossProfit + operatingIncome per fiscal year, upserts one synthetic income row per fy_end tagged `source='yfinance_history', period='FY'`. JSONB-merge order keeps EDGAR / FMP canonical values on overlap; yf only fills NULL keys. Wired as the `yf_history` step in `ingest_daily.py` with a Friday-only cadence guard (`date.today().weekday() == 4`) because annual statements refresh quarterly + Yahoo's income_stmt is slow + rate-limited.
  2. **Income loader cap 8 → 24**: V (and any filer that mixes quarterly + annual rows in `fundamentals`) was returning only 2 FY rows inside the 8-row income window, blocking `compute_eps_cagr_3y` at its `len(annual) < 4` guard even when EDGAR had full FY data going back 18 years. 24 covers four fiscal years of mixed cadence reliably.
  - **V verification after the fix**: `eps_cagr_3y=13.37%` (8.28 → 10.20 diluted EPS over 2y, GAAP), `gross_margin_trend=-0.08%` (V's gross margin is essentially stable). PEG recomputed from canonical inputs jumped to 2.37 (vs Yahoo info-derived 1.40 we had before) — more transparent and method-traceable. **Visa now shows all 9 Valuation+Quality cells non-null end-to-end.**

- [x] **/api/prices 500 fix** — shipped 2026-06-09. `/api/prices/{ticker}` was crashing with 500 because the SQL used `(:lookback || ' days')::interval` for the WHERE clause; the `||` concatenation operator collides with psycopg's parameter binding on some code paths. Rewrote to use `date_trunc`-style arithmetic with the bucket / lookback inlined as server-trusted integers from the range_map. No Timescale dependency, deterministic bucket boundaries. Production check: `/api/prices/V?range=20y` returns 222 points spanning 2008-03-12 → 2026-06-05.
- [x] **fcf_yield precision wave** — shipped 2026-06-09 (PR #70). Two pieces:
  1. **FMP key-metrics-TTM ingestor** (`ingestors/fmp_key_metrics.py`): pulls daily-current `marketCap`, `freeCashFlowYieldTTM`, `peRatioTTM`, `debtToEquityTTM`, ROE/ROA for the equity universe. Stored as a synthetic income row at `(ticker, today-1, income)` tagged `source='fmp_key_metrics'`. Adds a 5th candidate to `estimate_market_cap()` via the existing `cross_validated()` path — no compute change. Free-tier coverage: 20/51 tickers (31 return 402); rest of universe still served by the standard FMP fundamentals + EDGAR + yfinance path.
  2. **EDGAR concept-priority fall-through** (`ingestors/sec_edgar_facts.py`): `_extract_rows` used to `break` after the first XBRL concept in its priority list that had ANY observation, silencing later concepts even when the primary one had no observation for the current `period_end`. NVDA was the canonical victim — it switched from `PaymentsToAcquirePropertyPlantAndEquipment` to `PaymentsToAcquireProductiveAssets` around 2020-Q3, so every post-2020 cash_flow row landed with null capex → null freeCashFlow → fcf_yield 0.07%. Fix: drop the `break`, gate each assignment with `if payload.get(our_name) is None` so earlier concepts still win on overlap, later concepts fill the gaps where the earlier one has no observation. **V-shaped recoveries observed:**
     - NVDA fcf_yield 0.07% → **2.40%** (TTM FCF $3.6B → $119B, matches analyst LTM)
     - NVDA gross_margin: None → **71.07%**
     - NVDA operating_margin: None → **60.38%**
     - NVDA gross_margin_trend: None → **+14.14%** over 3y
     - UNH gross_margin newly computed at 18.80% (insurance-business correct)
     - AMZN fcf_yield now -0.37% — reflects the current AI-capex spike rather than the previous false-positive
  3. **Diagnostic scripts** that drove the debug session land alongside: `dump_v_xbrl_concepts.py` now accepts a ticker arg, plus `dump_nvda_cashflow.py` and `dump_nvda_capex_obs.py`.
- [x] **Crypto universe expansion** — shipped 2026-06-09 (PR #71 + #72 + #73). Coinbase `CRYPTO` list grows 2 → 8 pairs (BTC, ETH, SOL, AVAX, LINK, DOT, DOGE, XRP). All listed on Coinbase Exchange (same public API, no new auth). `UNIVERSE = _RAW + CRYPTO` so `by_asset_class("crypto")` works uniformly. `coinbase_eod.DEFAULT_PAIRS` derives from `universe.CRYPTO` so adding a coin is a one-line change. URL convention: clients send `SOL-USD` (dash, URL-safe), worker normalizes `dash → slash` for the universe + SQL lookup (`SOL/USD` is the canonical form). Cathie's prompt grows a "Crypto allocation (4th asset class, not a sector)" subsection — 0–20% sleeve cap, ≤10% per coin, BTC+ETH ≥50% of any non-zero sleeve, no stablecoins, bull scenarios must cite on-chain economics. Production check: `/api/prices/SOL-USD?range=max` returns history from 2021-06-02 (Coinbase listing day).
- [x] **BRK.B SEC ticker alias** — shipped 2026-06-09 (PR #73). SEC tickers feed uses `BRK-B` (dash) while our universe uses `BRK.B` (dot, matching Alpaca + most vendors). `_load_cik_map` now mirrors each dashed SEC ticker under the dotted form too, so the EDGAR + companyfacts lookups succeed for the universe ticker without per-call patching. Generalizes to any future dual-class name (BF-B, etc.).
- [x] **`fiscal_year_end_month` per ticker → precise FCF decomposer anchoring** — shipped 2026-06-14. `TickerMeta.fy_end_month: int = 12` added to `universe.py`; non-December overrides for AAPL=9, MSFT=6, NVDA=1, AVGO=10, LRCX=6, CRWD=1, HD=1, DECK=3, COST=8, WMT=1, PG=6 (verified against latest 10-K period_end). `_decompose_cumulative_ytd_to_ttm` accepts the hint and prefers month-match over the prior ±45-day day-delta when looking for both the prior-YTD anchor and the last-FY annual; falls back to the existing day-delta + max-value heuristic when the hint is absent or matches nothing. Wired through `sum_ttm_fcf` → `_load_fundamentals_latest` consumer via META lookup. UNH/AMZN/COIN edge-case verification awaits operator-side `--only features coverage` rebuild — this PR ships the loader-side fix; fcf_yield precision improvement is the observable downstream.
- [x] **2-pass persona architecture — SHIPPED as v2, default since #87 (2026-06-10)** — research per ticker → ONE construction call → `normalize_book` deterministic sum=1.0 → risk gateway (#94) → one row per persona. The aggregator cash-inference became log-only belt-and-suspenders (#90). Original design note: — Surfaced 2026-06-09 while diagnosing Warren's last batch (8% BRK.B + 9 × 0% + 12% cash = 20%). Root cause: each `run_thesis()` call sizes its position independently with no view of siblings. PR #76 patched the aggregator to infer cash from the coverage gap, but that's a bandage on a structural problem: a human PM doesn't size each name in isolation, they research individually and then allocate across the surviving set with relative-comparison reasoning. Plan:
  1. New `agents/portfolio_construction.py` — one LLM call per persona per batch. Input: all per-ticker theses + constraint envelope (single-name cap, sector cap, cash range). Output: a `Proposal` whose `target_weights + cash = 1.0` enforced by Pydantic. The persona's prompt does the relative comparison ("MSFT 9/10 vs MCO 7/10 → size MSFT heavier") instead of the aggregator reaching for an average.
  2. `run_thesis()` slimmed down — no `target_weight`, just `conviction` + thesis body. Lower per-call token budget (~$0.03 vs $0.05).
  3. `persona_batch.py` flow: research all tickers → portfolio construction → persist single proposal row. Errors per ticker still don't take down a persona, but construction sees the surviving set.
  4. `/api/proposals/{personaId}` aggregator returns the construction output directly — drop the cash-inference safeguard from PR #76 (or keep as a belt-and-suspenders log).
  - Foundation for a **lightweight risk gateway** below: construction-time LLM already enforces caps, so the gateway becomes a thin validator (verify `target_weights + cash = 1.0`, every ticker is in universe, no single-name > persona's `max_single_name`) rather than the "reject + retry" flow originally scoped. This reduces Phase C risk-gateway work meaningfully.
  - Cost delta: Warren ~$0.50 → ~$0.58/batch (research $0.03 × 10 + construction $0.08). Across the desk ≤ $3/week. Negligible vs the coherence win.
  - ~3–4 hours of careful work; touches agents/, persona_batch.py, schemas, main.py aggregator. **Schedule as the first PR of the next session.**
- [ ] **Cross-source disagreement dashboards** — `cross_validated()` already logs candidate spread + decision on disagreement (GOOGL 2.06× was the first audited case). Surface the log stream in Grafana so we can audit which tickers are systemic (GOOGL dual-class causes a consistent 2× spread between `close × diluted` and `payload_income`; that's a feature flag away from a per-ticker rule, but we'd want to see the pattern first). Same panel watches debt_to_equity + gross_margin once those use cross_validated(). Pre-req: the Grafana wiring task above.
- [x] **GOOGL dual-class mcap rule** — shipped in PR #67. `MULTI_CLASS_TICKERS = {"GOOGL"}` in `features/compute.py:86` short-circuits `estimate_market_cap` to the payload_income mcap path, bypassing the cross_validated max-pick heuristic. The 2.06× disagreement warning no longer fires on every build. To extend: add tickers only after verifying close × diluted gives a *smaller* mcap than the canonical company-level reported value (BRK.B doesn't qualify — its FMP diluted share count is already A-equivalent).
- [x] **BRK.B yfinance hit-rate monitoring** — shipped 2026-06-14. `_step_coverage_audit` now cross-joins each `market_cap_usd` gap against today's `fundamentals` rows where `payload->>'source'='yfinance'`. A gap_market_cap ticker with no yfinance row today means the 3rd-tier fall-through also failed — surfaced as a focused `features.mcap_gap_yf_also_failed` warning (separate from the noisier coverage_gap stream, alert-target-ready in Grafana). Returned in the step result as `mcap_gap_yf_also_failed: list[str]`. The broader `coverage_gap` stream stays intact for fcf_yield/peg/gross_margin nulls.

#### 2026-06-11 codebase audit — Step 0 hotfixes shipped, Steps 1–2 queued

Full audit doc: **`docs/improvement-plan-2026-06-11.md`** (severity-ordered
findings P0–P3 + operator checklist). Shipped in the audit session:

- [x] **P0-1: OHLCV canonical-day dedup** — see the resolved ⚠️ note under
  "Maximum-history backfill" below. Code + `006_ohlcv_canonical_day.sql`;
  operator apply + feature rebuild + canary re-run pending.
- [x] **P0-2: `/api/proposals` aggregator v2-aligned** — pre-fix it unioned
  the last 20 analyst_reports rows (≈20 weekly batches under v2's
  one-row-per-batch layout), resurrecting dropped tickers as "ghost
  positions" and averaging cash across months. Now scopes to
  `MAX(as_of_date)` only; aggregation extracted to `_aggregate_book` with 6
  regression tests (`tests/test_main_api.py`); v2 `notes_to_manager`
  restored in the response.
- [x] **P0-3: yfinance promoted to core dependency** — the `[backfill]`
  extra never made it into the Cloud Run image, so the daily `yf_shares` /
  weekly `yf_history` steps silently no-op'd in prod (ImportError swallowed
  per ticker, step reported ok=True). Now a core dep + missing-install
  fails the step loudly. **Worker image rebuild required.**
- [x] **Constant-time bearer compare** (`hmac.compare_digest`) on the worker.

Queued from the same audit (ordered):

- [x] **CI workflows** (Step 1) — **shipped 2026-06-11**.
  `.github/workflows/ci.yml`: ruff (blocking) + pytest (blocking) + mypy
  (non-blocking, 216-error backlog) on worker; tsc + next lint on web.
  Ruff backlog 102 → 0. Web `.eslintrc.json` added (next lint would have
  hung CI on its first-run interactive prompt without it). gitleaks
  pre-commit config added — devs run `pre-commit install` once.
- [x] **Batch execution model** (Step 2) — **partially shipped 2026-06-11**:
  `deploy_cloud_run.ps1` now passes `--no-cpu-throttling` (takes effect on
  next deploy), so BackgroundTasks keep CPU after the 202. The structural
  fix — Cloud Run **Jobs** for ingest/persona_batch — stays open for
  Phase C proper.
- [x] **Ingest advisory lock** — **shipped 2026-06-11**.
  `db.try_advisory_lock("ingest_daily")` wraps the whole run; a duplicate
  trigger returns a fast no-op `advisory_lock` step.
- [x] **Chat abuse guards** — **shipped 2026-06-11**. Worker: message ≤
  4K chars (400), history sanitized (≤20 turns, role-validated, content
  truncated), and a chat-only daily budget pool
  (`LLM_MAX_DAILY_COST_CHAT_USD`, default $2) so public chat can't starve
  the Friday batch. Edge proxy: per-IP rate limit (10/min, best-effort
  per-isolate) + size pre-checks before the worker is touched.
- [x] **SPY canary as automated orchestrator step** — **shipped
  2026-06-11**. New `jobs/spy_canary.py` + `canary` step (13th) in
  `ingest_daily`: >100bps divergence vs Yahoo fails the run (exit 1 /
  Sentry); Yahoo outage logs + skips. Adjusted-price policy decision
  still open (P2-1) — current empirical diff 2.62bps says the comparison
  is sound as-is.

### Week 5 — Frontend wire-up + baseline backtest + weight-distribution telemetry
- [x] **Leaderboard tab** reads from `persona_performance` — **shipped 2026-06-12**: real 1y† (hypothetical-blended, footnoted) / 90d / sharpe_30d / mdd_30d / NAV per persona via `/api/performance`; hit-rate column shows "—" until closed-lot tracking. `lib/mock/performance.ts` DELETED.
- [x] **Cumulative return charts**: read real persona equity curve — **shipped 2026-06-12**. Landing hero (4 personas × dashed-hypothetical + solid-live segments + SPY from `/api/prices`), persona detail sheet (same split + caption), dashboard portfolio tab (followed persona, 180d re-based). `CumulativeChart` now merges by DATE (index-merge silently misaligned mixed calendars). New worker endpoints `GET /api/performance/{persona}` + `GET /api/portfolio/{persona}` with Edge proxies; client fetcher `lib/performance-data.ts` with module-level cache.
- [x] **Attribution breakdown** — **shipped 2026-06-12 (#107)**. `risk/attribution.py`: `pnl_d = qty_{d−1} × Δclose` over daily snapshots (close-priced flows → contributions sum to the period return; live check: ray MTD −1.9343% vs sum −1.9345%). `GET /api/attribution/{persona}?period=mtd|7d|30d`. **Frontend table shipped 2026-06-13**: `AttributionTable` in the persona detail sheet (period toggle MTD/7d/30d, rows sorted by |pnl|, header shows period total return) + Edge proxy `/api/attribution/[personaId]`.
- [ ] **Backtest mode**: replay 90 days → simulate 90 days of paper trades → baseline Sharpe/MDD
- [x] **Weight distribution telemetry** — **shipped 2026-06-12 (#106)** as the canary's 6th check: per-book histogram logged every batch (`canary.weight_telemetry`, Grafana-scrapeable) + hard violation when ≥3 active names sit within 1pp of the persona cap (§11 bimodality proxy) → Sentry. The §10 conviction-only-schema decision now has its telemetry feed; decide after a few weekly batches.
- [x] **Enable Voyage embeddings on prod — DONE 2026-06-12** (secret + SA grant + deploy; similarity recall fires in the WEEKLY BATCH prompt assembly as `sim=` — chat memory itself stays Phase D, see #102). Original steps: (rolled forward from Phase B 2026-06-05). Decision was to ship chat with `VOYAGE_API_KEY` absent on Cloud Run; `fetch_memory_recall` falls back to recency. By Phase C Week 5 `persona_memory` should have ~100+ rows (4 personas × 10 tickers × 3-5 weekly batches), at which point similarity-based recall starts surfacing meaningfully more relevant past theses than recency. Steps: (1) `gcloud secrets create VOYAGE_API_KEY` + populate, (2) add `,VOYAGE_API_KEY=VOYAGE_API_KEY:latest` to `deploy_cloud_run.ps1` --set-secrets, (3) redeploy worker, (4) compare a chat sample with vs without — confirm the 'sim=X' recall-tag actually fires + that the surfaced past theses are more topical than what recency picked. Cost stays $0 (Voyage free tier 200M tokens/month; pilot uses ~500K).
- [ ] **Push notification on rebalance**: FCM → browser
- [x] **Sentry alert: paper engine error → page within 5 min** — **done 2026-06-12 (#108 + operator)**. Engine failures never reached Sentry before (per-persona isolation swallowed exceptions; structlog errors aren't auto-captured) — now explicit `capture_exception`/`capture_message`, and the operator created the issue-alert rule (runbook §1-2b).
- [x] **Skeleton/error states** — done across reports/proposals (06-05) and performance/portfolio/cards (#103): loading pulses, empty states, fetch-failure fallbacks ("—").
- [x] **Quant data integrity gates** — shipped 2026-06-14. Three pieces, all in `risk/paper_engine.py`:
    1. **Point-in-time guard**: `_load_latest_bars` accepts `as_of`; when set, bars are upper-bounded to `ts::date <= as_of`. `_run_persona` now passes `today` through both call sites so a backtest replay or back-dated perf-row regeneration cannot read tomorrow's prices into yesterday's NAV.
    2. **Write-time integrity gate** (`validate_bars`, pure function, 6 unit tests): refuses to write `persona_performance` when (a) any held ticker is unpriced, (b) any held ticker's newest bar is older than `REFUSE_WRITE_STALE_DAYS=14` (twice the warn threshold; long ingest outage), or (c) any open/close is non-finite or non-positive. Failure pages Sentry + returns `{"integrity_gate": "failed", "reasons": [...]}` instead of shipping a stale Sharpe/MDD.
    3. **Adjusted-price policy**: documented at the top of `paper_engine.py` — we use UNADJUSTED Alpaca IEX (equities/ETFs) + Coinbase (crypto). Splits/dividends are not applied; for pilot-scale + 90-day backtest the relative comparison stays apples-to-apples, and a corporate-actions feed is a Phase D-class workstream. Invalid-feature handling is covered by the existing `sharpe_30d` / `max_drawdown` guards (return None on degenerate input) — no change needed there.
- [ ] **fcf_yield precision edge cases** (Quant) — UNH (5.7% vs real ~3%), NVDA (0.07%), AMZN (0.35%), COIN (14.7%) read off-band on the Phase B shipping pass. Sanity bound (±100%) prevents these from polluting the LLM prompt, but precision is too loose for risk-gated backtests. Root causes:
    1. **Sparse FY anchors** — some issuers' fundamentals history doesn't include a row ~12 months back, so the TTM decomposition falls back to `max(window)` (= last full FY annual; up to 12 months stale for fast growers).
    2. **Alternating null filings** — some tickers have duplicate filing rows where one is a restatement/erratum with no FCF data; the Phase B fix filters nulls before capping the loader window, but a few cases still slip through when filings span > 2 fiscal years.
    3. **One-time spikes** — COIN's TTM includes the late-2025 crypto turnover boom; the value is real but unrepresentative of forward yield.
  - **Fix path**: dedicated daily mcap source (FMP `key_metrics` endpoint) + FY-aware ingestion that records `fiscal_year_end_month` per ticker so the decomposer can pick anchors precisely. Ingestor → new column `key_metrics_market_cap` on `ticker_features` → `estimate_market_cap()` adds it as a 5th candidate. Phase C because it touches the ingest plane, not just compute.
- [x] **Leakage tests for backtest mode** — **shipped 2026-06-05** (PR descendants of #42). 4 mock-session unit tests in `tests/test_prompt_assembler.py`: (1) `fetch_inputs(as_of=X)` passes `cutoff=X` to ≥5 queries and all date binds ≤ X, (2) `as_of=None` still binds today, (3) memory recall recency path respects cutoff, (4) memory recall without as_of omits the cutoff clause from SQL (not just binding None). Phase C Week 5 will add the same-shape gate at LEADERBOARD/BACKTEST METRIC WRITE-TIME — different layer, same guarantee.
- [x] **SEC EDGAR XBRL fundamentals parser** (Quant) — **shipped 2026-06-02 (pre-Phase B)**. Took the simpler path via SEC's pre-parsed XBRL JSON (`data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`) instead of parsing XML with arelle. New `ingestors/sec_edgar_facts.py` wired as step 5 of the orchestrator. Coverage jumped from FMP free's 20/42 tickers to **39/42** (HON, LLY, MA, NEE, LIN, etc. now reachable). 3 still missing for reasons unrelated to gating: BRK.B (SEC uses dash not dot in ticker map), ASML + TSM (foreign filers — submit 20-F, no us-gaap facts JSON). JSONB-merge upsert preserves any FMP-only fields, so the two sources coexist. FMP Starter $14/mo decision becomes moot for the 39 covered names; only useful if the 3 foreign filers become critical.
- [x] **Maximum-history backfill across all sources** (Quant + Infra) — **shipped 2026-06-02 (pre-Phase B)** via new `jobs/backfill_history.py` with `--source {alpaca|coinbase|fred|yahoo|all}` flags. Results from the one-shot run:
  - **Alpaca OHLCV (equities)**: 73,486 rows, 51 tickers, 2020-07-27 → 2026-06-01 (~6 yrs, Alpaca IEX feed start). 23 sec.
  - **Coinbase BTC/ETH**: 7,664 rows, 2015-07-20 → today (~11 yrs). 18 sec.
  - **FRED (37 series)**: 237,404 rows, each series back to its earliest available date (UNRATE 1948→, T10YIE 2003→, etc.). 101 sec.
  - **SEC XBRL companyfacts**: 7,178 rows, 39/42 tickers, ~9 yrs per ticker. Done as part of the XBRL parser task above (one ingestor serves both daily + backfill).
  - **yfinance**: **shipped 2026-06-02** — 178,276 rows across 41 tickers, 20-yr depth (2006-05 → today). BRK.B failed (Yahoo uses `BRK-B` with dash, our universe has `BRK.B` with dot — known mapping issue). Rows tagged `source='yahoo'`. Daily cron untouched (yfinance remains opt-in via `[backfill]` extras).
  - **⚠️ Subtle issue surfaced by mixing sources — RESOLVED 2026-06-11** — `ohlcv_1d` PK is `(ticker, ts)` where `ts` is `TIMESTAMPTZ`. Alpaca writes `04:00:00+00:00`, Yahoo writes `00:00:00+00:00`. Same calendar date, different `ts` → both rows coexisted for the ~6-year overlap window. The 2026-06-11 audit found this was NOT just a backtest double-count risk: the **production feature builder** (`compute.py::_load_ohlcv`) read both rows, silently halving every row-window feature's horizon (`ret_30d` ≈ 15 trading days, `vol_30d` / `rsi_14` / `sma_*` / `volume_z` all distorted) — the risk-register "feature builder bug propagates as LLM-blessed thesis" scenario, live. Fixed by `006_ohlcv_canonical_day.sql` (deletes duplicates, canonical source per day: alpaca/coinbase > yahoo; also deletes orphaned `ticker_features` rows) + `DISTINCT ON (ticker, ts::date)` dedup in `_load_ohlcv` and `/api/prices` + `backfill_yahoo` now skips days covered by a non-yahoo source. **Operator must re-run `ingest_daily --only features coverage` + SPY canary after applying 006.** See `docs/improvement-plan-2026-06-11.md` P0-1.
  - **FMP fundamentals**: 5 yrs annual on free tier (already accumulated via daily cron). 30y available on $79/mo Premier — not pursued; XBRL covers what we need free.
  - **NewsAPI**: ❌ not backfillable on free tier (30-day rolling cap). Defer indefinitely.
  - **SEC EDGAR filings**: shipped 2026-06-01 separately (220 filings, ~1.5 yrs per ticker). Extending to 5y is `DEFAULT_PER_FORM_LIMIT = {"10-K": 5, "10-Q": 20}` then re-run — operator decision when LLM personas need more management-prose context.
  - **Total**: ~325K new rows across all sources, ~3 min wall-clock. Storage well within Neon free 0.5 GB.
  - **Acceptance**: backtest harness in Phase C Week 5 has 6 yrs equity history, 11 yrs crypto, multi-decade macro, and 9 yrs of SEC-source fundamentals — meets the "≥3 yrs price / ≥5 yrs macro / ≥5 yrs fundamentals" bar.

**Compression note**: previously three weeks. The biggest sacrifice is the
length of real-life paper track record collected by end of Phase C — only
days, not weeks. The 90-day backtest baseline becomes the credibility anchor
instead of real elapsed paper time.

### Acceptance criteria
- ✅ Leaderboard shows real 30-day Sharpe and MDD per persona
- ✅ Cumulative return chart on landing page matches sum of paper trade P&L
- ✅ Backtest 90-day Sharpe is within expected range per archetype (Warren ~1.3, Cathie ~0.9, Ray ~1.5, Peter ~1.4)
- ✅ 0 risk-gate violations slipped to paper execution

### Lessons from Phase C (running list — close out with the phase)

Full presentation-ready write-ups with symptom→hunt→root-cause per bug
live in **`docs/case-studies.md`** (CS-1…CS-10, kept for the final
project talk). The distilled rules:

1. **Silent failure is THIS project's #1 bug class.** Four real
   incidents shared one shape — an error swallowed without a sound:
   `except ImportError → no_data` made a missing dependency report
   ok=True (CS-3); `setdefault` let an LLM-volunteered `as_of` beat the
   server for weeks (CS-4); a JSON parser that tolerated trailing but
   not leading prose threw away valid retry books as "char 0" (CS-5);
   `suppress(AttributeError)` hid that SQLAlchemy Rows are immutable,
   so working similarity recall self-labelled "recency" forever (CS-6).
   Rule: every caught exception either logs loudly with context or
   re-raises; `suppress`/`except: pass` need written justification.
2. **A verification instruction is code too** — "check the logs for
   sim=" was unverifiable by construction (the tag was never logged,
   and broken even in the prompt). When docs claim "verify by X",
   confirm X can actually emit a signal.
3. **"tokens_out=4527" + "error at char 0" = suspect the parser, not
   the model.** Read the evidence pair, not the exception string.
4. **--no-cpu-throttling ≠ instance immortality.** The Friday batch
   died with its idle-reaped instance at 23:02 (CS-8). Request-scoped
   compute is a countdown timer for 15-minute jobs. **Resolved
   2026-06-13**: ingest + persona_batch moved to **Cloud Run Jobs**
   (run to completion, Cloud-Scheduler-triggered) — `deploy_cloud_run_jobs.ps1`
   + `docs/runbooks/cloud-run-jobs.md`. Service keeps the HTTP surface.
5. **Ops docs must speak the operator's shell.** A bash `echo -n` run
   in PowerShell corrupted the Voyage secret (CS-9). This team's shell
   is PowerShell; write runbooks for it.
6. **Fixing observability surfaces hidden bugs.** The Cloud Run Jobs
   migration (#116) didn't just stop batches from dying — by honoring
   exit codes (the Service ignored them), its first test-run exposed a
   9-day equity-OHLCV freeze: `_step_ohlcv_equity` sent the full
   universe (crypto included) to Alpaca, which rejected the crypto
   symbol and failed the whole batch (CS-12, #119). Source-specific
   ingest must be fed source-specific tickers (`by_asset_class`).

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
- **From Week 1**: ✅ Sentry on web + worker (shipped 2026-06-01)
- **From Week 2 (originally planned)**: ~~Grafana Cloud — LLM cost~~
  - **Schedule slipped, functional equivalent shipped instead.** `llm_call_log` table (persona_id, stage, model, tokens_in, tokens_out, cost_usd, latency_ms, ts) populated per call. `check_daily_budget()` runs before every Anthropic call and **hard-pauses** the run when daily spend ≥ `LLM_MAX_DAILY_COST_USD` (default $20, set $5 in pilot .env). No alert → just refuses the call.
  - **Phase C work** (rolled forward): Grafana Cloud dashboard + Slack webhook alert at $5/$10/$20 thresholds. Same source data, just visualized.
- **From Week 4**: Simple `/status` page (last ingest, last persona run, paper engine health)
- **From Week 6**: Sentry alerts → email; cost alerts at $5/day, $10/day, $20/day thresholds (becomes the trip-line on the same data already collected)

### Secrets management
- Anthropic key, Alpaca key (when live), FMP key, NewsAPI key → GCP Secret Manager
- `WORKER_WEBHOOK_SECRET` rotated 2026-06-09 (leaked during a debug session); both Cloud Run secret + Vercel env now hold the new value.
- Firebase Admin SDK → Vercel env var (encrypted)
- **Never commit any key.** Pre-commit hook checks for common patterns.
- **Open**: Cloud Run worker is currently `--allow-unauthenticated` with bearer auth as the only guard. Phase D follow-up: switch to `--no-allow-unauthenticated` and have Vercel sign requests with an IAM token. Removes the bearer as a single point of failure if it leaks.

### Data resilience (cross-cutting, formalized 2026-06-09)
- **3-tier ingestion** is the standing pattern for fundamentals: FMP → SEC XBRL → yfinance (synthetic row). See architecture.md §6 "Data resilience" for the diagram.
- **When adding a new field**: add the GAAP concept to `sec_edgar_facts.py::CONCEPTS_*` first (free, canonical). If a meaningful slice of the universe doesn't tag it, extend `yf_shares.py` payload + `compute.py` fall-through. Never call yfinance from `compute.py` directly — it stays an ingestor side, so feature builds remain pure-SQL and deterministic.
- **When a UI field is blank for a ticker**: `scripts/inspect_ticker_features.py <T>` is the diagnostic entry point. The four sections it prints (`ticker_features` latest row → fundamentals coverage → field presence → dry-run compute) localize the dropout to one of {EDGAR concept mismatch, payload null, compute sanity drop, persistence}.
- **Sanity envelopes** apply uniformly across sources (`FCF_YIELD_SANITY_BOUND`, `EPS_CAGR_SANITY_BOUND`, `PEG_SANITY_BOUND`, `DEBT_TO_EQUITY_SANITY_BOUND`, `MARGIN_SANITY_LOW/HIGH`, P/E ≤ 500). A yfinance glitch can't ship absurd values into the LLM prompt.
- **Cross-validation** is via `compute.py::cross_validated(candidates, max_spread, pick_on_disagreement)` — today only mcap uses it. Next wave: debt_to_equity, gross_margin, FCF.

### CI / quality
- **From Week 1**: GitHub Actions running `npm run typecheck` + `npm run lint` on every PR
- **From Week 2**: Python `ruff` + `mypy --strict` on worker
- **From Week 4**: smoke test that hits `/api/health` on every PR
- **⚠️ Status check 2026-06-11**: none of the above was ever implemented —
  `.github/workflows/` does not exist, ruff backlog is 102 findings, mypy
  strict reports 216 errors, and the promised secret-scanning pre-commit
  hook is absent. Scheduled as Step 1 of `docs/improvement-plan-2026-06-11.md`.

### Documentation
- Keep `architecture.md` and `personalities.md` in sync with code; treat as ADRs
- After each phase, write a **"Lessons from Phase X" subsection inside
  this file** (§3 has Phase A's, §4 has Phase B's — added 2026-06-12).
  Policy changed from separate `docs/retro-phase-X.md` files: lessons
  belong inline where the next phase gets planned, and one growing
  roadmap file beats a graveyard of unopened retro files. `docs/` stays
  reserved for individually-referenced artifacts (adr/, runbooks/,
  grafana/, one-off audits).
- Update `Plan.md` (this file) if scope changes
- `CLAUDE.md` at repo root is the AI-session operator handbook —
  rewritten 2026-06-12 for zero-context handoff (state, invariants with
  incident rationale, process rules, debugging entry points, backlog).
  Update it in the same PR as any change it describes.
- Presentation decks (`*.pptx`) are local-only as of 2026-06-12
  (`decks/`, gitignored) — the public repo stays lean; `build-deck.js`
  regenerates.
- **`docs/case-studies.md`** — presentation-ready bug case studies
  (CS-1…CS-10: symptom → hunt → root cause → fix → lesson, with PR
  links). Add a CS entry whenever a nontrivial bug is fixed; it is the
  raw material for the final project talk. Distilled rules go into the
  per-phase Lessons subsections here.

---

## 10. Open decisions

### Decided (2026-06-05 stocktake)
| Decision | Choice | Date | Rationale |
|---|---|---|---|
| Chat model | **(a) Sonnet 4.6 always** | 2026-06-05 | Chat backend not yet built; will start with Sonnet, revisit when chat volume > 500 msg/day per persona |
| Persona count for pilot | **(a) all 4** | 2026-05-26 | Budget allows; Ray runs on parallel RegimeReport schema |
| Persona run cadence | **Weekly (Fri close), not daily** | 2026-06-04 | Daily = 4×30×$0.02 ≈ $72/mo. Weekly = ~$10/mo, sufficient for paper-pilot. Hard-coded in `persona_batch.py` design (pending ship) |
| Screen funnel | **Deferred** — universe is 50 names, no Haiku screen needed yet | 2026-06-03 | Revisit when universe > 200 |
| Cathie sector cap | **0.50 → 0.70** | 2026-06-12 | The 50% cap contradicted her "concentrated by S-curve sector" mandate — she breached it twice in live batches even after explicit gateway feedback (67% → 56%; case study CS-11: role beats rule). The cap now encodes the mandate; her risk budget stays governed by VaR99 ≤ 8.5% + single-name 16% + crypto-sleeve rules |

### Still open
| Decision | Options | Recommendation | Decide by |
|---|---|---|---|
| Manager curation | (a) ship as-built (4 portfolios side-by-side) (b) add 5th persona "Mara" that curates into 3 named portfolios | **(a) for pilot, revisit at user count > 20** | Before Phase D F&F onboarding |
| Cathie crypto exposure | (a) equity proxies only (COIN, MSTR) (b) spot BTC/ETH via Coinbase | **(a) for pilot**, (b) requires Coinbase OAuth + additional disclosures | Before Phase C paper execution wires Coinbase adapter |
| Backtest window | (a) rolling 90d (b) fixed 2024-01 → 2025-12 | **(b)** — reproducible baseline everyone can compare against | Start of C (wk 4) |
| Weight decision authority | (a) LLM outputs `target_weight` directly (current schema) (b) LLM outputs `conviction ∈ [0,1]`, Python maps to weight | **Start with (a); refactor to (b) if mode-collapse telemetry flags it.** (b) is architecturally cleaner but reduces LLM-side explainability | End of C (wk 5) — after weight-distribution telemetry in Phase C Week 5 |

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

- [x] **All 4 personas** writing real Sonnet 4.6 theses on the agreed cadence (✅ weekly batch live since 2026-06-05; v2 + gateway since 06-11/12) (**weekly Fri close** per 2026-06-04 decision; daily reserved for Phase F live mode), validated by passing the same <2% schema-fail gate the backtest harness measures
- [ ] **30+ days** of paper P&L track record, accurate Sharpe/MDD displayed
- [ ] **Self** running paper successfully for 30+ days, no manual intervention required
- [ ] **3 F&F users** onboarded, each following a different persona, with their own dashboard
- [ ] **Lawyer consult** complete; written advice on file
- [ ] **Cost stable** under $200/mo for 4 weeks (current trajectory: weekly cadence projects ~$10–15/mo for LLM alone, well under)
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
| 0.5 | 2026-06-11 | **Codebase audit + Step 0 hotfixes.** New `docs/improvement-plan-2026-06-11.md` (P0–P3 findings + 4-step plan). Shipped: OHLCV canonical-day dedup (006 + compute/_load_ohlcv/prices/backfill fixes — the mixed-source ⚠️ note in §5 was found to also distort PRODUCTION features, not just backtests), `/api/proposals` v2 aggregator fix (ghost-positions), yfinance promoted to core dep (prod yf steps were silently no-op), constant-time bearer compare. §5 gains a "2026-06-11 codebase audit" subsection; §9 CI section gains an honest status check (no workflows exist). Removed duplicated cross-source-dashboards bullet. |
| 0.6 | 2026-06-12 | **Phase C Week 4 core live.** Audit Steps 1–2 landed (#93: CI ruff-0 + pytest gate, gitleaks pre-commit, ingest advisory lock, chat abuse guards + chat budget pool, nightly SPY canary step, `--no-cpu-throttling`). Risk gateway (#94) inside construction retry loop. PaperEngine v1 (#95) + `FEATURE_PAPER_EXECUTION=true` (#96) — Week-4 ledger tasks (engine / order ledger / MTM / performance writer) marked done, LISTEN/NOTIFY dropped for the simpler daily-step design. §0 baseline rewritten. `CLAUDE.md` added. |
| 0.8 | 2026-06-12 | **Phase C risk/analytics layer complete (#105–#108, deployed same day).** Gateway gains parametric VaR99 (calibrated per persona) + drawdown floor (live track only) + Ray's regime gate; weight-distribution telemetry as canary check 6 (§11 mode-collapse tripwire); ticker-level attribution (`/api/attribution`, contributions sum to period return); paper-engine failures now page via explicit Sentry capture + operator alert rule. Live smoke caught warren/cathie's pre-#94 books over SECTOR caps — Friday's batch re-shapes them via retry feedback. Remaining in Phase C: 90d backtest baseline, attribution UI table, quant edge cases; tech debt: Cloud Run Jobs, mypy ledger. |
| 0.7 | 2026-06-12 | **Audit Step 4 — docs closed out.** Frozen-book 1y backfill run on prod (#100, 251 days × 4 personas, seam exact); frontend performance/portfolio swap shipped (#103, `lib/mock/performance.ts` deleted, hypothetical segments dashed + captioned); Week-5 leaderboard/chart tasks marked done. Retro policy decided: per-phase "Lessons" subsections live INSIDE this file (§4 gains Phase B's 7 lessons; no separate retro files). `CLAUDE.md` rewritten as a zero-context AI operator handbook. Decks moved to local-only `decks/` (gitignored). mypy CI-blocking via pyproject debt ledger (#99). |

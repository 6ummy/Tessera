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
- **7 production ingestors**: Alpaca EOD, Coinbase EOD, FRED macro (37 series), FMP fundamentals, NewsAPI, SEC EDGAR (10-K + 10-Q with GCS raw HTML), SEC XBRL companyfacts (structured fundamentals, fills FMP gap)
- **51-ticker universe** spanning sectors each persona cares about
- **Deterministic feature builder** — ret_*, vol_30d, rsi_14, sma_{20,50}, volume_z. 13/13 hypothesis tests pass.
- **Daily orchestrator** (`ingest_daily.py`) — 8 sequential steps, idempotent, CLI flags
- **Phase C historical backfill** (`backfill_history.py`) — pre-shipped 2026-06-02: 6yr Alpaca + 11yr Coinbase + full FRED depth (~325K rows total) so backtest harness has multi-year input from day one
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

Phase A wired the entire data plane. **Quant (예슬, 준원) and LLM Pipeline (윤채, 한솔) work on top of what's already there** — nobody needs to wait on infra.

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

What's missing for Phase B that needs to be added to `features/compute.py` (Quant owns this):
- **FCF yield** — needs `ohlcv_1d.close * shares_outstanding` and `fundamentals.cash_flow.free_cash_flow`
- **PEG ratio** — `forward P/E ÷ EPS growth 3yr`
- **Debt-to-equity** — from `fundamentals.balance_sheet`
- **EPS CAGR 3y / 5y** — derived from `fundamentals.income_stmt` over consecutive periods

Pattern to follow: each new feature is a pure pandas function inside `features/compute.py`, with a property-based test in `tests/test_features.py`. Goes through the same `ticker_features` upsert path — no schema change needed (jsonb column or extend the table; ADR if extending).

For **risk gateway prep** (Phase C precursor): compute per-ticker volatility and correlation matrices using existing `ohlcv_1d`. Don't store yet — Phase C is when persona positions exist and we need to gate them.

**LLM Pipeline track (윤채, 한솔) — assemble persona prompts**

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
| **LLM Pipeline** (윤채, 한솔) | `apps/worker/tessera_worker/agents/` | `LLM_pipeline_demo.md` | `python -m tessera_worker.agents.demo_warren_aapl` |
| **Quant** (예슬, 준원) | `apps/worker/tessera_worker/features/` | `Quant_demo.md` | `python -m tessera_worker.features.demo_fcf_yield` |
| **Anyone — "what's in the DB?"** | same `features/` folder | (no doc, just run it) | `python -m tessera_worker.features.demo_data_explorer` |

Both demos connect to Neon, run in ~5 seconds, print readable output, and are designed to be **forked** into your own feature/persona work. They live inside the package (not in `scripts/`) so `python -m tessera_worker.<...>.demo_*` works the moment `pip install -e .` is done — no extra setup.

> **Read this section once, then jump straight to your track's demo and markdown.** Each track owns its own folder; you do not need to touch the other track's files to be productive.

---

##### 🧠 If you're on **LLM Pipeline (윤채 + 한솔)** — start here

**Already done for you by 정우** (zero setup on your side):
- ✅ Anthropic API key is in Secret Manager (prod) and in the KakaoTalk pin (local). Don't generate a new one.
- ✅ Sentry is wired — your `raise`/`except` inside any agent module shows up in the `tessera-worker` Sentry project automatically.
- ✅ `personalities.md` is the canonical persona spec. CODEOWNERS lets all four team owners (정우, 윤채, 한솔, 예슬) approve changes — but big voice changes get a 카톡 heads-up first.
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
- ✅ `ticker_features` is the existing feature table, already populated daily with `ret_*, vol_30d, rsi_14, sma_{20,50}, volume_z`. Your new features add columns / rows to this same table — no parallel store.
- ✅ Property-test scaffolding exists in `tests/test_features.py` with 13 passing tests — copy the pattern when you add a new feature.
- ✅ Cron job auto-runs your new features once they're plugged into `compute.py`'s `build()` — no extra deployment step.

**Your scope** (Week 2): extend `features/compute.py` with Phase B features that the personas need (FCF yield, PEG, EPS CAGR, debt/equity, gross margin trend). Each feature is a small pandas function + a property test + a column migration. Risk gateway code lives in `risk/` and is Phase C — you can sketch it now but don't ship until Week 4.

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
- Day 2: ship `fcf_yield` as a real `ticker_features` column (migration + `build()` integration + test)
- Day 3: `peg_ratio` (forward P/E ÷ EPS growth — needs FMP analyst estimates, else trailing proxy)
- Day 4: `eps_cagr_3y` (3 consecutive annual income rows)
- Day 5: `debt_to_equity` + start sketching the Phase C precursors (correlation matrix, sector exposure)

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
| TSM FCF yield 48% — ADR share-count units mismatch | Quant | Quant demo's bar chart shows TSM as a wild outlier |

Pick one as your first PR. They're all real, small, and improve the downstream signal quality for everyone.

#### When something looks wrong

- **Cloud Run cron run failed?** Check `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=tessera-worker AND severity>=ERROR" --freshness=1d`. Anything user-visible should also surface in Sentry → `tessera-worker` project.
- **DB has stale data?** Check the latest `fetched_at` on the suspected table (`SELECT MAX(fetched_at) FROM news`). If older than 24h, the cron skipped or failed.
- **API rate-limited mid-run?** All ingestors are idempotent — just trigger again. `ON CONFLICT DO UPDATE` handles duplicates.

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
- [x] **SEC EDGAR filings ingestor** — shipped 2026-06-01. New 7th step in daily orchestrator. Per ticker: 2 × 10-K + 4 × 10-Q (≈1.5 yrs of management prose). Body excerpt (8KB) into `filings.text_summary`, raw HTML to GCS `tessera-raw/edgar/{accession}.html`. Skip-if-already-have on accession means daily runs are no-ops once steady-state. Smoke-test verified end-to-end with AAPL + MSFT (12 filings, 49 MB HTML, 32s local run). Full universe run scheduled with next Cloud Run cron. Frees 예슬 to focus on features + risk gateway prep for Phase C.

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
- [x] **SEC EDGAR XBRL fundamentals parser** (Quant) — **shipped 2026-06-02 (pre-Phase B)**. Took the simpler path via SEC's pre-parsed XBRL JSON (`data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`) instead of parsing XML with arelle. New `ingestors/sec_edgar_facts.py` wired as step 5 of the orchestrator. Coverage jumped from FMP free's 20/42 tickers to **39/42** (HON, LLY, MA, NEE, LIN, etc. now reachable). 3 still missing for reasons unrelated to gating: BRK.B (SEC uses dash not dot in ticker map), ASML + TSM (foreign filers — submit 20-F, no us-gaap facts JSON). JSONB-merge upsert preserves any FMP-only fields, so the two sources coexist. FMP Starter $14/mo decision becomes moot for the 39 covered names; only useful if the 3 foreign filers become critical.
- [x] **Maximum-history backfill across all sources** (Quant + Infra) — **shipped 2026-06-02 (pre-Phase B)** via new `jobs/backfill_history.py` with `--source {alpaca|coinbase|fred|yahoo|all}` flags. Results from the one-shot run:
  - **Alpaca OHLCV (equities)**: 73,486 rows, 51 tickers, 2020-07-27 → 2026-06-01 (~6 yrs, Alpaca IEX feed start). 23 sec.
  - **Coinbase BTC/ETH**: 7,664 rows, 2015-07-20 → today (~11 yrs). 18 sec.
  - **FRED (37 series)**: 237,404 rows, each series back to its earliest available date (UNRATE 1948→, T10YIE 2003→, etc.). 101 sec.
  - **SEC XBRL companyfacts**: 7,178 rows, 39/42 tickers, ~9 yrs per ticker. Done as part of the XBRL parser task above (one ingestor serves both daily + backfill).
  - **yfinance**: **shipped 2026-06-02** — 178,276 rows across 41 tickers, 20-yr depth (2006-05 → today). BRK.B failed (Yahoo uses `BRK-B` with dash, our universe has `BRK.B` with dot — known mapping issue). Rows tagged `source='yahoo'`. Daily cron untouched (yfinance remains opt-in via `[backfill]` extras).
  - **⚠️ Subtle issue surfaced by mixing sources** — `ohlcv_1d` PK is `(ticker, ts)` where `ts` is `TIMESTAMPTZ`. Alpaca writes `04:00:00+00:00`, Yahoo writes `00:00:00+00:00`. **Same calendar date, different `ts` → both rows coexist** (not what we want; backtests would double-count). Workaround for now: queries use `DISTINCT ON (ticker, ts::date) ... ORDER BY ... CASE source WHEN 'yahoo' THEN 1 WHEN 'alpaca' THEN 2 END` to prefer the deepest source per calendar day. Permanent fix is a Phase C migration: either (a) normalize `ts` to a `DATE` (loses intraday capability we don't yet need), or (b) add a `(ticker, ts::date)` unique constraint and pick a canonical source per day. **demo_data_explorer.py already uses pattern (a)** so the sparklines + coverage numbers are correct.
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

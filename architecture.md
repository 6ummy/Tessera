# Tessera Architecture

> An agentic research desk. Four AI analyst personas with distinct philosophies
> each publish a long-term portfolio side-by-side. Paper-trading MVP today,
> live-execution ready by design.

---

## 1. Product overview

| | |
|---|---|
| **Brand** | Tessera ("a small tile in a mosaic" — each analyst is a piece of the whole) |
| **Stage** | Paper-trading pilot LIVE (2026-06-12): real data, weekly LLM theses behind a risk gateway, nightly paper execution. Phase C nearly done; Phase D (user auth) next. |
| **Audience** | Long-term retail investors (US) — not scalpers, not pros. |
| **Horizon** | Months to years. Daily-batch desk, no intraday signals. |
| **Surface** | Web app (Next.js on Vercel). Mobile-responsive. |
| **Today's pilot scope** | 3 users (self, friends, family). Paper trading only. |

## 2. Design principles

1. **LLMs write theses. Code computes numbers.** Language models hallucinate prices, returns, P&L — so they don't compute them. Every percentage, weight, and chart is calculated by deterministic Python on raw data. The model writes the *why*, not the *what*.
2. **Paper-first, live-ready.** The same code path serves paper and live execution. Live trading is one feature flag away once compliance and capital allow it.
3. **Distinct philosophies, not consensus.** The four analysts are designed to disagree. A value investor and a disruptive-growth investor *should* reach opposite conclusions about the same name. Their disagreement is the signal.
4. **Cost scales with the desk, not with users.** Persona analysis is batched once per session on shared market data. Three users or three hundred, the LLM bill is the same.
5. **Developer-experience matters.** Tools chosen so the operator manages one Vercel dashboard, one Firebase console, one Cloud Run service, one Neon DB — no AWS/GCP console mazes.

---

## 3. System architecture (target)

```
┌─ Data Plane ──────────────────────────────────────────────┐
│  EOD market data (Alpaca + Coinbase, free tiers)          │
│  Fundamentals/filings (FMP, SEC EDGAR)                    │
│  Macro (FRED)                                              │
│  News (NewsAPI / Reddit)                                  │
│                          ▼                                 │
│              Neon Postgres (TimescaleDB + pgvector)       │
│              - OHLCV daily, fundamentals, macro            │
│              - news text + embeddings                      │
│              - persona memory                              │
└──────────────────────────────────────┬─────────────────────┘
                                       │
┌─ Agent Plane (Cloud Run Jobs, batch) ────────────────────┐
│                                       ▼                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
│  │ Warren  │  │ Cathie  │  │  Ray    │  │ Peter   │     │
│  │ Value   │  │ AI/Cryp │  │ Macro   │  │ GARP    │     │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘     │
│       │ Haiku 4.5 screen → Sonnet 4.6 thesis             │
│       │ Output: AnalystReport (Pydantic JSON)            │
│       └────────────────┬──────────────────────┐          │
└────────────────────────┼──────────────────────┘──────────┘
                         ▼
┌─ Decision Plane (pure Python, no LLM) ────────────────────┐
│  Quant Validator   : ticker exists, schema valid          │
│  Risk Gateway      : single-name ≤15%, sector ≤30%, etc.  │
│  Citation Check    : cited news IDs resolve to real rows  │
└──────────────────────────────────┬────────────────────────┘
                                   ▼
┌─ Execution Plane (Adapter pattern) ───────────────────────┐
│  Paper Engine  (default) ──► Neon ledger table           │
│  Alpaca live   (flagged) ──► Alpaca paper/live (US)      │
└──────────────────────────────────┬────────────────────────┘
                                   ▼
┌─ User Plane ──────────────────────────────────────────────┐
│  Firestore (realtime sub) — selections, alerts, social    │
│  Vercel (Next.js)         — UI, chat, dashboard           │
└───────────────────────────────────────────────────────────┘
```

## 4. Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend hosting | **Vercel (Hobby)** | Zero-config Next.js, US-region default, free for pilot |
| Frontend framework | **Next.js 14 App Router + TypeScript** | RSC + server actions, mature |
| Styling | **Tailwind 3 + Radix primitives** | Claude-design palette (cream + coral + ink) |
| Charts | **Recharts** | React-native, deterministic, lightweight |
| Auth | **Firebase Auth** (Google/Apple SSO) | 5-minute setup, free tier covers pilot |
| Realtime user data | **Firestore** | Native client subscriptions, push fan-out |
| Push | **Firebase Cloud Messaging** | Free, integrated |
| Agent workers | **Google Cloud Run Jobs** | Scale-to-zero, 60-min job limit, same GCP project as Firebase, free-tier sufficient for pilot |
| Time-series + vector DB | **Neon Postgres** + TimescaleDB + pgvector | One DB for OHLCV, fundamentals, embeddings, ledger; serverless branching; Vercel-friendly |
| Event bus | **Postgres LISTEN/NOTIFY** | Kafka is overkill at pilot scale |
| Brokerage (paper) | **Alpaca** (US stocks + crypto via one API) | Single adapter, paper/live toggle |
| LLM | **Anthropic Claude** | Haiku 4.5 (1st-pass screen) + Sonnet 4.6 (thesis & chat) + Opus 4.7 (weekly meta-review) |
| Observability | Sentry + Grafana Cloud free tier | Sufficient for pilot |

## 5. The four analysts

| | Warren | Cathie | Ray | Peter |
|---|---|---|---|---|
| Archetype | Value | Disruptive Growth (AI/Crypto) | Macro Hedger | GARP |
| Age | 67 | 32 | 58 | 44 |
| Heritage | American (Nebraska) | Korean-American | Italian-American | Irish-American |
| Lives | Omaha, NE | Mission District, SF | Greenwich, CT | Brookline, MA |
| Background | UNL → Columbia MBA; founded value partnership 1991 | Stanford CS → Two Sigma → a16z crypto → own fund | NYU → Wharton MBA; founded macro fund 1999 | BC → MIT Sloan; Fidelity → Wellington → own fund |
| Voice | Plainspoken Midwestern, short sentences, period-heavy | Forward-leaning, scenario-structured, links arXiv | Measured, probability-laden, regime-thinking | Conversational, observational, store-walker |
| Holdings | 7–12 names, FCF yield > 6%, 5+ yr | 15–25 names, AI/crypto/biology, bear/base/bull | 8–14 ETFs, 2×2 regime grid | 12–20 names, PEG < 1.2, GARP |
| Photo | warren.jpg | cathie.jpg | ray.jpg | peter.jpg |

Full biographical detail, voice rules, and chat fine-tuning specs live in
[personalities.md](personalities.md). That file is the source of truth for
system prompts when wiring real LLM calls.

---

## 6. Current state (what is actually built)

As of 2026-06-15 this is a **working LLM research desk on real data with
a credibility-anchored 90-day backtest**: Phases A + B + C all shipped.
Real Sonnet 4.6 theses land weekly behind a full risk gateway, chat
streams live, the paper engine fills each persona's book against a $100K
paper account nightly, and the 2026-06-14 backtest baseline produced
per-archetype Sharpe/MDD on look-ahead-free replays (Warren 1.28 / Cathie
3.21 / Peter 2.81 / Ray 1.96 over 9/13 weeks, the remaining 4 weeks
limited by a one-time prod cap collision since fixed via the
`cost_namespace` isolation in #132). The only remaining mocks are the
Phase-D account demos (dashboard "My portfolio" positions + Social feed)
and auth (see "Still mocked" below). **Phase D (Firebase Auth + F&F
follows) is the next milestone.**

### Frontend (4 routes on Vercel)
- **Marketplace** (`/`) — landing page = persona grid; click any card opens a slide-over detail sheet. Header logo is an inline SVG mosaic mark (coral / ink / sage tiles).
- **Persona detail sheet** — biography, signature signals, real 1-year performance curve vs S&P 500 (single solid line per persona; hypothetical backfill blended in, flagged at the data layer), real recent reports (accordion), real latest portfolio, and live chat.
- **Chat with analyst** — real Sonnet 4.6 SSE stream (worker `agents/chat.py` → Edge proxy). Ticker-aware RAG, persona voice specs, abuse guards (rate limit + size caps + chat-only budget pool).
- **Proposals** (`/proposals`) — two tabs: "By analyst" (4 real books side-by-side from `/api/proposals`) and "Consensus" (cross-analyst agreement table).
- **Dashboard** (`/dashboard`) — user account view with tabs: My portfolio, Leaderboard, Social feed. URL-synced (`?tab=…`). Still mock-backed pending `persona_performance` swap.
- **How it works** (`/how-it-works`) — customer-facing explanation of pipeline, safety, and compliance posture.
- **Vercel Cron endpoints** — `/api/cron/daily` (`30 21 * * 1-5`) and `/api/cron/weekly` (`0 22 * * 5`), both forwarding to the Cloud Run worker with IAM identity tokens.

### Phase A backend (shipped, runs against production Neon)
- **Neon Postgres** provisioned (us-east-1, free tier), `001_init.sql` applied. 14 tables + 3 extensions (TimescaleDB, pgvector, uuid-ossp).
- **Python worker** (apps/worker) with FastAPI skeleton, structured JSON logging, SQLAlchemy + psycopg3 session pool.
- **7 ingestors operational**: Alpaca EOD (equities + ETFs), Coinbase EOD (BTC, ETH), FMP fundamentals (`/stable/` endpoints), FRED macro (37 series — yields, inflation, labor, growth, money, FX, energy, commodities, credit spreads, VIX), NewsAPI (ticker-tagged headlines), SEC EDGAR (10-K + 10-Q with GCS raw HTML — added 2026-06-01 in Phase B), **SEC XBRL companyfacts** (structured GAAP fundamentals via `data.sec.gov/api/xbrl` — added 2026-06-02; fills FMP free-tier gaps so coverage went 20/42 → 39/42 equity tickers). All idempotent via `ON CONFLICT DO UPDATE`.
- **Universe**: 51 tickers (49 equities + 2 crypto pairs) spanning the sectors each persona cares about.
- **Feature builder** (`compute.py`): deterministic pandas/numpy module. Reads `ohlcv_1d` + `fundamentals`, writes `ticker_features`. Computes ret_{1d,5d,30d,90d,1y}, vol_30d, rsi_14, sma_{20,50}, volume_z, plus latest fundamentals-derived `fcf_yield`, `fcf_yield_normalized` (median of last 5 FY FCFs / mcap, #134), `peg`, `eps_cagr_3y`, `debt_to_equity`, `gross_margin`, `gross_margin_trend`, `gross_margin_qtr_yoy_chg` (Friday-only quarterly YoY, #133), `market_cap_usd`, and `operating_margin`. **This is the only path numerical features reach the LLM**. Feature tests pin the math and edge cases.
- **Daily orchestrator** (`jobs/ingest_daily.py`): 8 sequential steps (ohlcv_equity → ohlcv_crypto → macro → fundamentals → edgar_facts → news → filings → features). CLI flags `--only`/`--skip`. Exit code 0/1 maps to Cloud Run Job success/failure.
- **Connection smoke test** (`scripts/check_connections.py`): verifies all 6 external services + redacts secrets from any error output.
- **Production state right now** (snapshot 2026-06-01, after first Cloud Run-driven run + EDGAR step shipped):
  - `ohlcv_1d`: ~14,600 rows (53 tickers × ~270 trading days)
  - `ticker_features`: ~14,500 rows
  - `macro_series`: ~650 rows from 20 FRED series
  - `fundamentals`: ~300 rows (FMP free tier blocks some premium endpoints; `fmp.fetch_skip` logs are expected)
  - `news`: ~1,650 rows tagged to 42 tickers
  - `filings`: 12 rows so far (AAPL + MSFT smoke-test set); first full universe run pending. Raw HTML in `gs://tessera-raw/edgar/`.
- **Canary**: SPY 1y return vs Yahoo Finance reference — diff **0.49 bps** (well inside 100 bps threshold).
- **Cloud Run worker deployed** (2026-06-01): `tessera-worker` service at `https://tessera-worker-ffr7g3a76a-ue.a.run.app` (us-east1, `--allow-unauthenticated` + shared bearer in app code, non-root container, 1 vCPU / 1 GiB / max 2 instances). Vercel Cron now calls `WORKER_WEBHOOK_URL` and gets `{status:"queued", workerStatus:200}` back.

### Daily data flow (production)

```
┌────────────────────────────────────────────────────────────┐
│  REAL WORK — automatic, no human in the loop                │
│                                                              │
│  Vercel Cron (21:30 UTC, Mon–Fri; declared in vercel.json)  │
│        ↓ POST /api/cron/daily  (Bearer CRON_SECRET)         │
│  Vercel edge route (apps/web/app/api/cron/daily/route.ts)   │
│        ↓ POST WORKER_WEBHOOK_URL                            │
│        ↓ (Bearer WORKER_WEBHOOK_SECRET, 8s fetch timeout)   │
│  Cloud Run worker  /jobs/ingest-daily                       │
│        ↓ FastAPI BackgroundTask returns 202 immediately     │
│        ↓ (heavy work continues async; cron not blocked)     │
│  tessera_worker.jobs.ingest_daily.run()                     │
│        ↓ 8 sequential steps, each idempotent                │
│        1. Alpaca EOD       → ohlcv_1d (equities, 42)        │
│        2. Coinbase EOD     → ohlcv_1d (crypto, BTC + ETH)   │
│        3. FRED macro       → macro_series (37 series)       │
│           ├── yields:     DGS2/10/30, T10Y2Y, breakevens    │
│           ├── inflation:  CPI, core CPI, PCE, core PCE      │
│           ├── labor:      UNRATE, payrolls, jobless claims  │
│           ├── growth:     INDPRO, retail sales              │
│           ├── money:      M2, Fed BS, broad USD             │
│           ├── FX (9):     USD/EUR, JPY, KRW, CAD, CHF,      │
│           │              CNY, GBP, MXN, INR                 │
│           ├── energy:     WTI, Brent, nat gas, jet fuel     │
│           ├── metals/ag:  copper, wheat (monthly)           │
│           ├── credit:     HY OAS, IG OAS                    │
│           └── risk:       VIX                               │
│        4. FMP fundamentals → fundamentals (30-day cache,    │
│                              free tier: ~20/42 tickers)     │
│        5. SEC XBRL facts   → fundamentals (JSONB merge,     │
│                              fills FMP gap, ~39/42 tickers) │
│        6. NewsAPI          → news                           │
│        7. SEC EDGAR        → filings + raw HTML to GCS      │
│                              (10-K + 10-Q, skip-if-have)    │
│        8. Feature builder  → ticker_features                │
│        ↓ UPSERT (ON CONFLICT DO UPDATE)                     │
│  Neon Postgres   (single source of truth for all data)      │
│  GCS gs://tessera-raw/edgar/    (raw SEC filing HTML)       │
│        ↓ stdout (structlog JSON)                            │
│  GCP Logging  +  Sentry (errors only)                       │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  HISTORICAL BACKFILL — one-time per source (Phase C)        │
│  (not part of nightly cron; an operator runs these manually)│
│                                                              │
│  $ python -m tessera_worker.jobs.ingest_daily \              │
│        --only ohlcv_equity --since 2018-01-01                │
│                                                              │
│  Same 8 ingestors, wider time window.                       │
│  Upserts are idempotent → safe to re-run.                   │
│                                                              │
│  Source         depth available     why                      │
│  ─────────────  ──────────────────  ────────────────────────│
│  Alpaca         ~7 years            free tier maximum        │
│  Coinbase       10+ years           public API, no limit     │
│  FRED           per-series earliest UNRATE 1948→ etc.        │
│  FMP            5 yrs annual        free tier (30y on paid)  │
│  NewsAPI        ❌ 1 month only      free tier hard cap      │
│  SEC EDGAR      extend depth        2K+4Q → 5K+20Q config    │
│                                                              │
│  Status today: only EDGAR backfilled (220 filings, 1.5 yrs   │
│  per ticker). Others have just the rolling-window depth      │
│  the daily cron has accumulated. Phase C Week 5 task         │
│  "Maximum-history backfill across all sources" closes this   │
│  gap so the backtest harness has multi-year input.           │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  OBSERVATION — what humans run to check on it               │
│                                                              │
│  $ gcloud logging read \                                     │
│      "resource.labels.service_name=tessera-worker" \         │
│      --freshness=10m                                         │
│      → reads recent Cloud Run log events                    │
│      → "is it running? which step? passed/failed counts?"   │
│                                                              │
│  $ python -m scripts._counts                                 │
│      → SELECT count(*) on 5 core tables                     │
│      → "did the row counts go up after the run?"            │
│                                                              │
│  Sentry UI → tessera-worker / tessera-web Issues             │
│      → any unhandled exception during the run               │
└────────────────────────────────────────────────────────────┘
```

**FRED update cadence per series** — daily cron pulls all 37 series, but each source updates at its own pace; FRED returns the latest value regardless. Most series (25/37) are truly daily — yields, FX, oil, nat gas, credit spreads, VIX. **Weekly**: jobless claims (ICSA), Fed balance sheet (WALCL). **Monthly**: all inflation indices (CPI, PCE), labor stats (UNRATE, payrolls), growth (INDPRO, retail sales), M2, wages, copper/wheat. So `macro_series` has new rows daily for the daily ones, and "no-op" daily inserts for the monthly ones (UPSERT just rewrites the same value). The personas can treat every macro lookup as "latest known" — the DB always has a row.

**Data lives only in Neon.** Cloud Run is stateless — when a job finishes the worker memory is freed and the container may scale to zero. Local `.env` files hold API keys but no data. To onboard a new dev: `git clone` + `.env` filled from the shared KakaoTalk credential pin + `pip install -e .` is enough to run the same code against the same Neon DB.

**Concurrent-run note — RESOLVED 2026-06-11**: `ingest_daily.run()` now holds a Postgres advisory lock (`pg_try_advisory_lock(hashtext('ingest_daily'))`, see `db.try_advisory_lock`) for the whole run. A second trigger landing mid-run (manual curl + scheduled cron) returns immediately as a no-op `advisory_lock` step instead of running the pipeline in parallel. Session-level locks free on disconnect, so a crashed run can never wedge the next one. **Refined 2026-06-15 (CS-14, #143)**: the helper `conn.commit()`s right after acquiring — SQLAlchemy 2.0 future-mode opens an implicit transaction on the first `execute()`, so without the commit the lock connection sat idle-in-transaction and Neon's `idle_in_transaction_session_timeout` reaped it mid-run; the dead connection then made the end-of-run `pg_advisory_unlock` throw out of the context manager, flagging a fully-successful 15-step Job as exit 1. Session-level locks survive a commit (only `pg_advisory_unlock`/disconnect release them), so the lock still protects the whole run; the unlock is additionally `suppress`-wrapped (#140) so a benign teardown error can never flip a green run to failed.

**Long-job survival note (Phase C todo)**: Cloud Run **Services** allocate CPU only while handling a request by default. FastAPI's `BackgroundTask` runs *after* the response is sent — so if the instance scales to zero before the task finishes, the task is killed mid-way. We observed this on the first deploy: FMP fundamentals can take 15+ minutes (many 402s with backoff), and the instance idled out. Two fixes when full-run reliability matters:
- **(a)** Set `--cpu-throttling=false` on the Service so CPU stays allocated. Costs slightly more (charged per CPU-second always, not just during requests).
- **(b)** Switch the ingest from Cloud Run **Service** to Cloud Run **Job**. Jobs are designed for batch and run to completion regardless of timeout.
- Phase B daily runs are usually fine (steady-state, ~5 min total because FMP skips fresh tickers). Phase C will pick (a) or (b) before the first persona depends on ingest reliability.
- **Update 2026-06-11**: option (a) shipped — `deploy_cloud_run.ps1` passed `--no-cpu-throttling`. It mitigated but didn't cure: CS-8 (2026-06-12) showed the weekly batch still died at 23:02 when the idle instance was reaped 15 min after the 202.
- **RESOLVED 2026-06-13** — option (b) shipped. `ingest_daily` and `persona_batch` now run as **Cloud Run Jobs** (run to completion regardless of HTTP lifecycle), triggered by Cloud Scheduler. The Service keeps the HTTP surface (`/api/*`, chat) + the `/jobs/*` endpoints as a manual fallback. See `apps/worker/scripts/deploy_cloud_run_jobs.ps1` + `docs/runbooks/cloud-run-jobs.md`. Job test-run verified the full 14-step ingest completes — and, because Jobs honor exit codes (the Service didn't), it immediately surfaced CS-12: `_step_ohlcv_equity` had been sending crypto pairs to Alpaca's stock feed, failing the whole equity batch and freezing equity OHLCV for 9 days (fixed #119 — equity step now sends `by_asset_class("equity")+("etf")` only).

**Canonical-day note (resolved 2026-06-11)**: mixing the Alpaca daily feed (bars stamped `04:00:00+00`) with the one-time Yahoo backfill (stamped `00:00:00+00`) left the same trading day stored twice in `ohlcv_1d` for the ~6-year overlap window — and the production feature builder read both rows, silently halving every row-window feature's horizon (`ret_30d`, `vol_30d`, `rsi_14`, `sma_*`, `volume_z`). Fixed by migration `006_ohlcv_canonical_day.sql` (canonical source per day: alpaca/coinbase > yahoo) plus `DISTINCT ON (ticker, ts::date)` dedup in `compute._load_ohlcv` and `/api/prices`, and a covered-day skip in `backfill_yahoo`. Full post-mortem: `docs/improvement-plan-2026-06-11.md` P0-1.

### External data sources (what we ingest, what it costs, why)

| Source | Auth | Cost | What we pull | Cadence | Destination table |
|---|---|---|---|---|---|
| **Alpaca** | API key + secret | Free (IEX feed only) | EOD OHLCV for 49 US equities + ETFs | Daily, last 30d window | `ohlcv_1d` (source='alpaca') |
| **Coinbase Exchange** | None — public API | Free, unmetered | Daily candles for 8 pairs: BTC, ETH, SOL, AVAX, LINK, DOT, DOGE, XRP (all `*/USD`). Pair list derives from `universe.CRYPTO` so adding a coin is one line. | Daily, last 30d | `ohlcv_1d` (source='coinbase') |
| **FRED** (St. Louis Fed) | API key | Free, unmetered | 37 macro series — yields, CPI/PCE, unemployment, M2, Fed BS, broad USD, VIX, **9 FX pairs** (USD/EUR, JPY/USD, KRW/USD, CAD/USD, CHF/USD, CNY/USD, USD/GBP, MXN/USD, INR/USD), **WTI + Brent + nat gas + jet fuel**, **copper + wheat** (monthly), **HY + IG credit spreads** | Daily, last 90d | `macro_series` |
| **FMP** (Financial Modeling Prep) | API key | Free tier (some premium endpoints 402) | Annual income / balance / cashflow as JSON | 30-day cache per ticker | `fundamentals` |
| **FMP key-metrics-TTM** | same API key | Free tier (~20/51 tickers; 31 return 402 — paid endpoints) | TTM `marketCap`, `freeCashFlowYieldTTM`, `peRatioTTM`, `debtToEquityTTM`, ROE/ROA. **Daily-current** mcap candidate (5th in `estimate_market_cap`) since the close-times-shares candidates can drift 2–3× when share counts in the filing payload are stale. | Daily, ~10s for universe | `fundamentals` (synthetic income row at `(ticker, today-1, income)`, `source='fmp_key_metrics'`) |
| **NewsAPI** | API key | Free tier (100 req/day) | Ticker-tagged headlines + body excerpts | Daily, last 24h | `news` |
| **SEC EDGAR** | `User-Agent` header (name + contact email) | Free, unmetered | 10-K (annual) + 10-Q (quarterly) full filings | Weekly (skip if accession already stored) | `filings` (meta + 8KB excerpt) + GCS (raw HTML) |
| **SEC XBRL companyfacts** | same `User-Agent` | Free, unmetered | Structured GAAP fundamentals — revenue, op income, FCF, EPS, shares, balance sheet items, etc. SEC's pre-parsed XBRL JSON, no XML parsing needed. 40/42 equity tickers (BRK.B now resolved via SEC's `BRK-B` ↔ universe `BRK.B` cik_map alias, 2026-06-09; ASML / TSM still skipped — foreign filers without us-gaap facts JSON). Concept-priority lists no longer break on the first match — they fall through so filers that switched GAAP concept names mid-history (NVDA: `PaymentsToAcquirePropertyPlantAndEquipment` until 2020, `PaymentsToAcquireProductiveAssets` after) get covered end-to-end. | Daily (cheap, idempotent) | `fundamentals` (JSONB merge with FMP) |
| **yfinance** (Yahoo, unofficial) | None | Free, scraped — no SLA | Last-resort fallback for `sharesOutstanding`, `marketCap`, `trailingPegRatio`, `grossMargins`, `trailingPE`, `forwardPE`. Used only when FMP + EDGAR leave the field blank (service / payment-network filers like V, MA whose XBRL doesn't expose these concepts). **Core worker dependency since 2026-06-11** — it previously lived in an optional `[backfill]` extra that never shipped in the Cloud Run image, so both yf steps silently no-op'd in prod (see improvement plan P0-3). | Daily, as a synthetic `(ticker, today, income)` row in `fundamentals` (source='yfinance') | `fundamentals` (JSONB merge; compute reads as final fall-through) |
| **yfinance history** (Yahoo, unofficial) | None | Free, scraped — no SLA, rate-limited (~4 rps) | `yf.Ticker(t).income_stmt` — annual diluted EPS / revenue / grossProfit / operatingIncome per fiscal year (~4 periods). Used to backfill EDGAR-sparse FY rows so `compute_eps_cagr_3y` + `compute_gross_margin_trend` can compute. | **Weekly** (Friday only, guard: `weekday() == 4`) — annual statements refresh quarterly + income_stmt endpoint is slow | `fundamentals` (synthetic FY rows per fy_end, `source='yfinance_history'`; JSONB merge fills NULL keys only) |

**Why some have keys and some don't**

- Authenticated APIs (Alpaca, FRED, FMP, NewsAPI) use per-account keys for rate limiting + billing. Each Tessera contributor gets their own personal key when they're set up.
- Coinbase splits its surface: trading-related endpoints need API key + secret + passphrase, but **public market data is open**. We don't trade through Coinbase (Alpaca handles execution), so we get away with no key.
- SEC EDGAR is a US public-data mandate — anyone can pull SEC filings for free. There's no API key, but **the SEC requires a contact `User-Agent`** (e.g. `Tessera Pilot you@example.com`) so they can email the operator if a script misbehaves. Requests without one return 403.

**Why FMP fundamentals AND SEC EDGAR — they look duplicate**

- **FMP** gives us *numbers* (revenue, EBITDA, FCF) as clean JSON. Direct input to feature builder (FCF yield, PEG, debt ratio).
- **SEC EDGAR** gives us *prose* (MD&A, risk factors, business segment narrative). Direct input to LLM personas. Warren reading "why services revenue decelerated" needs the management's own words, not just a number.

→ FMP is *what*, EDGAR is *why*.

**Alternatives we considered and rejected**

| Alt | Why not |
|---|---|
| Binance (instead of Coinbase) | US regulatory restriction — Binance.com blocks US residents |
| CoinGecko / CMC | Aggregators — prices are weighted averages across venues, not real trade prices |
| Yahoo Finance scrape as primary | No stable API, ToS-grey area, anti-bot defenses. Re-introduced 2026-06-09 as a *fallback-only* path via `yfinance` for fields no other source provides (V's shares + grossMargins), bounded by the same sanity envelope as our own computations. Not trusted for primary feeds. |
| Polygon.io | Better data but paid ($30+/mo) — Alpaca free covers Phase A/B needs |
| IEX Cloud | Sunsetting in 2024 |

### Data resilience layer — 3-tier fall-through + cross-validation

A core lesson from Phase B was that **single-source fundamentals fail unpredictably across the universe**: FMP free tier blocks some tickers, FMP-served filings sometimes ship preliminary rows with most fields null, EDGAR's GAAP-concept tagging varies by filer (Visa reports capex under `PaymentsToAcquireProductiveAssets` not `PaymentsToAcquirePropertyPlantAndEquipment`), and service businesses like V / MA don't tag `GrossProfit` in XBRL at all. The "right" answer for one ticker is the wrong fallback for another.

So instead of picking a primary source and accepting its gaps, the worker applies a **layered resilience pattern**:

```
                primary           gap-fill          last-resort
  ┌────────┐   ┌─────────────┐   ┌──────────────┐
  │  FMP   │ → │ SEC XBRL    │ → │ yfinance     │ →  fundamentals
  │ (~5y)  │   │ (~9y, free) │   │ (synthetic   │     (jsonb merge,
  │ jsonb  │   │ jsonb merge │   │  today row)  │      source tag)
  └────────┘   └─────────────┘   └──────────────┘
       │             │                  │
       └──────────────┴──────────────────┘
                     │
                     ▼
          ┌──────────────────────────┐
          │  features/compute.py     │
          │  per-field newest-       │
          │  non-null walk +         │
          │  cross-source validation │
          └──────────────────────────┘
                     │
                     ▼
              ticker_features
              (UI / LLM / risk)
```

**Three layers, each idempotent:**

1. **FMP** (`fmp_fundamentals.py`) — annual income / balance / cash-flow filings as raw JSON. 30-day cache per ticker so the quota isn't burnt daily on quarterly data.
2. **SEC XBRL companyfacts** (`sec_edgar_facts.py`) — for every us-gaap concept we care about, walks alternative concept names in priority order (e.g. revenue tries `RevenueFromContractWithCustomerExcludingAssessedTax`, then `Revenues`, then `SalesRevenueNet`). For capex specifically the priority is `PaymentsToAcquirePropertyPlantAndEquipment` → `PaymentsToAcquireProductiveAssets` → `PaymentsForCapitalImprovements`. dei.EntityCommonStockSharesOutstanding is consulted as a shares-outstanding fallback. JSONB-merge upserts preserve FMP-only fields where they exist.
3. **yfinance** — split across two ingestors with different cadences:
   - **`yf_shares.py`** (daily) — Yahoo's own pre-computed ratios pulled from `yf.Ticker(t).info`: `sharesOutstanding`, `marketCap`, `trailingPegRatio` / `pegRatio`, `grossMargins`, `trailingPE`, `forwardPE`. Writes a single synthetic income row keyed `(ticker, today, income)` so it sits next to the EDGAR / FMP rows without colliding (different period_end). yfinance is **only consulted by compute** when the EDGAR-derived path returned None — never as primary truth. Same sanity envelope (PEG ≤ 100, margins in [-1, 1], P/E ≤ 500) applies; a Yahoo glitch can't ship absurd values into the LLM prompt.
   - **`yf_history.py`** (weekly, Friday only) — `yf.Ticker(t).income_stmt` returns the last ~4 fiscal years of GAAP-style line items (diluted EPS, revenue, grossProfit, operatingIncome). Writes one synthetic row per fy_end with `source='yfinance_history', period='FY'`. JSONB merge order keeps EDGAR / FMP canonical values on overlap; yf only fills NULL keys. Unlocks `eps_cagr_3y` + `gross_margin_trend` for filers whose XBRL is sparse on the FY annual concepts. Friday-only cadence because annual statements refresh quarterly and Yahoo's income_stmt endpoint is slow + aggressively rate-limited (~4 rps soft cap).

**At read time** (`features/compute.py::_load_fundamentals_latest`):

- Pulls up to **24 most-recent income rows per ticker** (was 8 originally; bumped 2026-06-09 after V — a filer that mixes quarterly + annual — was returning only 2 FY rows in the 8-row window, which blocks `compute_eps_cagr_3y` at its `len(annual) < 4` guard). 24 covers four fiscal years of mixed cadence reliably; memory cost is negligible.
- For each field group, walks the available rows **newest-first and fills per-field independently from the first non-null observation**. A `shares_basic` from FY2024 plus a `marketCap` from today's yfinance row is a coherent estimate, not a corruption.
- For `marketCap` specifically there are up to **four candidates** (`close × diluted`, `close × basic`, payload mcap from cash-flow, payload mcap from income). `estimate_market_cap()` uses the reusable `cross_validated()` helper: if candidates agree within `max_spread=2.0×` we trust the most-current; if they disagree we **pick the largest and log the disagreement** with all candidates and the chosen value. Rationale: undercount errors (missing share class, wrong-unit shares) are more common than overcount, and larger mcap → lower fcf_yield is the more conservative direction for the LLM prompt.
- The same `cross_validated()` helper is the foundation for broader cross-source validation as we add it: an EDGAR-computed gross_margin can be sanity-checked against a yfinance grossMargins, an FMP debt-to-equity against an EDGAR-derived one. Today only mcap uses the helper; the framework is in place.

**Why not collapse this into a single ingestor?** Each layer is independently observable. If yf_shares fails for a week, FMP + EDGAR keep flowing. If EDGAR adds a new concept, we add one line to `CONCEPTS_INCOME` without touching anything else. The fall-through is deterministic and replayable — re-running `build(tickers)` against a fixed snapshot gives byte-identical output.

**Debugging missing fields**: when a ticker shows blanks in the UI, the worker ships three single-purpose scripts that walk the same fall-through and report exactly where data drops out:

- `scripts/inspect_ticker_features.py V` — single ticker end-to-end: latest `ticker_features` row (what the UI reads), `fundamentals` coverage per filing_type, field presence in the latest payloads, and a dry-run compute against the current DB.
- `scripts/inspect_v_rows.py` — recent payload fields per filing_type for one ticker.
- `scripts/dump_v_xbrl_concepts.py` and `scripts/dump_v_dei.py` — peek at every concept a filer actually reports under us-gaap / dei, marking which ones our mapping already covers.

These were built on the V (Visa) debug session 2026-06-09 that drove the layered design; they generalize to any ticker.

### How to read the data we've stored

Six tables matter for downstream work (LLM, frontend, ad-hoc analysis):

```
ohlcv_1d           # prices (Timescale hypertable)
macro_series       # FRED series
fundamentals       # FMP, JSON blobs per period
news               # NewsAPI, embedding column ready for pgvector
filings            # SEC EDGAR (excerpt + GCS pointer)
ticker_features    # derived: ret_*, vol_30d, rsi_14, sma_*, valuation/quality
```

**Three access patterns:**

#### 1. Direct SQL — fastest for exploration
Connect with the `DATABASE_URL` from the team KakaoTalk credential pin (same DB everyone uses). From `psql`, DBeaver, Neon's web console, or any Postgres client:

```sql
-- Apple's last 5 trading days
SELECT ts, close, volume FROM ohlcv_1d
WHERE ticker = 'AAPL'
ORDER BY ts DESC LIMIT 5;

-- Latest features for the whole universe (one row per ticker)
SELECT DISTINCT ON (ticker)
       ticker, ts, ret_30d, rsi_14, vol_30d,
       fcf_yield, peg, eps_cagr_3y, debt_to_equity, gross_margin
FROM ticker_features
ORDER BY ticker, ts DESC;

-- Macro: today's yield curve shape
SELECT series_id, ts, value FROM macro_series
WHERE series_id IN ('DGS2','DGS10','DGS30')
  AND ts = (SELECT MAX(ts) FROM macro_series WHERE series_id='DGS10');

-- Recent news for one ticker
SELECT ts, source, title FROM news
WHERE 'NVDA' = ANY(tickers)
ORDER BY ts DESC LIMIT 10;

-- Apple's latest 10-K body excerpt (first 8KB)
SELECT filing_date, period_end, length(text_summary) AS chars, raw_gcs_uri
FROM filings
WHERE ticker = 'AAPL' AND filing_type = '10-K'
ORDER BY filing_date DESC LIMIT 1;
```

#### 2. Python from the worker — for new pipeline steps
Inside any module under `apps/worker/tessera_worker/`, use the existing session helper. Already-typed connection pool, no need to thread `DATABASE_URL`:

```python
from sqlalchemy import text
from tessera_worker.db import session_scope

with session_scope() as session:
    rows = session.execute(text("""
        SELECT ticker, close
        FROM ohlcv_1d
        WHERE ticker = ANY(:tickers)
          AND ts = (SELECT MAX(ts) FROM ohlcv_1d)
    """), {"tickers": ["AAPL", "MSFT"]}).all()
    for ticker, close in rows:
        print(ticker, close)
```

For full SEC filing text (not just the 8KB excerpt), pull the raw HTML from GCS:

```python
from google.cloud import storage
from urllib.parse import urlparse

uri = "gs://tessera-raw/edgar/0000320193-26-000013.html"  # from filings.raw_gcs_uri
parsed = urlparse(uri)
blob = storage.Client().bucket(parsed.netloc).blob(parsed.path.lstrip("/"))
html = blob.download_as_bytes()
```

**GCS auth note**: this requires per-user IAM access to the `tessera-498200` GCP project, granted by the project owner (정우). Each developer authenticates with their *own* Google account via `gcloud auth application-default login` — never share or reuse another teammate's credentials. See `Plan.md` §4 access pattern (c) for the full 4-step setup. Most Phase B work doesn't need GCS access — the 8KB excerpt covers standard prompt-assembly needs.

#### 3. HTTP API from the frontend — SHIPPED (Phase B/C)
The Next.js app reads real `/api/*` routes that proxy the Cloud Run
worker; the frontend never touches Neon directly. All performance/report
mocks are deleted (only Phase-D account demos + auth remain mocked — see
§6 "Still mocked"). Live routes (Next Edge proxy → worker; path shape is
the worker endpoint, e.g. `/api/reports/{persona}`):

```
GET  /api/reports/{persona}        analyst_reports → UI report cards
GET  /api/proposals/{persona}      current book (latest as_of_date only)
GET  /api/performance/{persona}    equity curve + metrics (hypothetical flag)
GET  /api/portfolio/{persona}      latest real paper snapshot
GET  /api/attribution/{persona}    ticker-level P&L (?period=mtd|7d|30d)
GET  /api/features/{ticker}        latest ticker_features row
GET  /api/prices/{ticker}          downsampled OHLCV (?range=…)
POST /api/chat/{persona}           SSE stream from Sonnet 4.6
```

Client fetchers live in `lib/analyst-data.ts` (reports/proposals/features)
and `lib/performance-data.ts` (performance/portfolio + cached hook); both
hold AbortControllers and module-level promise caches.

**Connection cheatsheet** — credentials always come from secrets store, never code:

| Caller | Where DATABASE_URL lives | How |
|---|---|---|
| Local Python (you running ingest) | `apps/worker/.env` | `python-dotenv` auto-loads on import |
| Cloud Run worker | GCP Secret Manager | `gcloud run deploy --set-secrets` mounts as env var |
| Local Next.js (npm run dev) | `apps/web/.env.local` | Next.js auto-loads `.env.local` |
| Vercel production | Vercel project env vars | Set in dashboard → Settings → Environment Variables |

### LLM pipeline (shipped in Phase B; v2 two-pass since 2026-06-10)

This is what sits on top of the data plane. It's the chain that turns the
Neon rows into a written thesis a persona could defend out loud. The data
plane is shipped; the LLM pipeline is the Week 2 / Week 3 work.

```
┌──────────────────────────────────────────────────────────────────┐
│  PER-(PERSONA, TICKER) THESIS GENERATION                          │
│                                                                    │
│  agents/persona_loader.py                                          │
│        ↓ parse personalities.md  →  {warren, cathie, ray, peter}  │
│        ↓                                                           │
│   ──────────────  Warren's system prompt (3.4K chars)  ─────────  │
│                                                                    │
│        ┌─────────────────────────────────────────┐                │
│        ↓                                         ↓                 │
│  persona spec               +  data inputs (per ticker × persona)  │
│  (from loader)                  ┌──────────────────────────┐      │
│                                 │ ticker_features (Quant)  │       │
│                                 │ fundamentals  (FMP+EDGAR)│       │
│                                 │ macro_series  (37 series)│       │
│                                 │ news          (last 7d)  │       │
│                                 │ filings       (10-K MD&A)│       │
│                                 │ ohlcv_1d      (20yr hist)│       │
│                                 └──────────────────────────┘      │
│        ↓                                         ↓                 │
│        └──────────────► merge ◄──────────────────┘                │
│                          ↓                                         │
│  agents/prompt_assembler.py        ← LLM Pipeline (shipped)        │
│        ↓ system = persona spec   (cache_control: ephemeral)        │
│        ↓ user   = data blocks    (features, fundamentals, …)       │
│                          ↓                                         │
│  agents/anthropic_runner.py        ← LLM Pipeline (shipped)        │
│        ↓ Claude API call (Sonnet 4.6 deep, Haiku 4.5 screen)       │
│        ↓ Pydantic validation, 1× retry on schema fail              │
│        ↓ log tokens + cost                                         │
│                          ↓                                         │
│  agents/citation_validator.py      ← LLM Pipeline (shipped)        │
│        ↓ verify every cited_news_id resolves in news table         │
│                          ↓                                         │
│  Neon  →  analyst_reports                                          │
│        (persona_id, ts, inputs_hash, parsed jsonb,                 │
│         raw_response, cost_usd)                                    │
│                          ↓                                         │
│  Frontend  →  /api/reports/{persona}  (Edge proxy → worker)       │
│        ↓ shipped 2026-06-05; lib/mock/reports.ts deleted          │
│  UI: persona thesis appears in the desk view                       │
└──────────────────────────────────────────────────────────────────┘
```

**Who owns what** (track-level, see CODEOWNERS for the GitHub handles that auto-route PR reviews):

| Module | Track | Status |
|---|---|---|
| `agents/persona_loader.py` | LLM Pipeline | ✅ shipped |
| `agents/prompt_assembler.py` | LLM Pipeline | ✅ shipped |
| `agents/anthropic_runner.py` | LLM Pipeline | ✅ shipped (FEATURE_REAL_LLM gate) |
| `agents/citation_validator.py` | LLM Pipeline | ✅ shipped |
| `agents/models.py` (`AnalystReport`, `Proposal`) | LLM Pipeline | ✅ shipped (re-export from `tessera_shared`) |
| `features/compute.py` — `fcf_yield` (TTM-decomposed cumulative-YTD, FX-converted, cross-validated mcap) | Quant | ✅ shipped 2026-06-04 |
| `features/compute.py` — `peg`, `eps_cagr_3y`, `debt_to_equity`, `gross_margin`, `gross_margin_trend`, `market_cap_usd`, `operating_margin` | Quant | ✅ shipped locally 2026-06-06 (`004_quality_features.sql` + latest-row fundamentals pass). Next: risk-gateway consumption and coverage/precision telemetry. |
| `apps/web/app/api/{reports,proposals,performance,portfolio,attribution,features,prices,chat}/[…]/route.ts` + UI swap | Frontend | ✅ shipped (reports/proposals/chat 06-05; performance/portfolio 06-12 #103; attribution endpoint 06-12 #107) — all `lib/mock/*` deleted except personas metadata |
| `agents/anthropic_runner.py` Ray-specific (`run_regime_thesis`, `RegimeReport`) | LLM Pipeline | ✅ shipped 2026-06-03 (parallel schema, `persona_id='ray'` discriminator in `analyst_reports`) |
| `agents/embeddings.py` + `prompt_assembler.fetch_memory_recall` (Voyage similarity, recency fallback) | LLM Pipeline | ✅ shipped 2026-06-05 (PR #44) |
| `jobs/backtest_harness.py` (point-in-time replay, separate `backtest_reports` table, retry + persist-unparseable) | LLM Pipeline | ✅ shipped 2026-06-05 (live verified 1.67% then 0% schema-fail rate) |
| `jobs/hallucination_canary.py` (5 invariant checks against most-recent batch; Sentry alert on fail) | LLM Pipeline | ✅ shipped 2026-06-05 |
| `jobs/persona_batch.py` (weekly Fri cron — loops personas × shortlist → calls runner) | LLM Pipeline | ✅ shipped 2026-06-05 (Vercel cron `0 22 * * 5` → `/jobs/persona-batch` → 31-cell batch + chained canary; replaces the prior TODO stub in `main.py`) |
| `/api/chat/[personaId]` SSE chat backend — worker `agents/chat.py` (6-part assembler + Anthropic stream) + FastAPI SSE endpoint + Next.js Edge proxy | LLM Pipeline | ✅ shipped 2026-06-05. 6 levels of ticker resolution + RAG over last 5 reports + ticker_features. Universal chat policies + per-persona chat fine-tuning spec parsed from personalities.md. |
| `analyst-chat.tsx` SSE consumer (fetch + ReadableStream; `lib/chat-stream.ts` async generator) + AbortController on unmount/persona switch | Frontend | ✅ shipped 2026-06-05. Mock `lib/mock/chat.ts` deleted. Starters extracted to `lib/chat-starters.ts`. |
| `/api/reports/[personaId]` + `/api/proposals/[personaId]` Edge proxies, worker endpoints `GET /api/reports/{persona}` + `GET /api/proposals/{persona}` in `main.py` reshape `analyst_reports.parsed` into uniform `{positions, cashWeight, regime?, asOf}` shape; client-side fetcher + skeleton/empty states in `lib/analyst-data.ts`; types in `lib/thesis-types.ts` | LLM Pipeline + Frontend | ✅ shipped 2026-06-05. Mock `lib/mock/reports.ts` + `lib/mock/proposals.ts` deleted. `lib/mock/performance.ts` + `lib/mock/portfolio.ts` retained pending Phase C paper-trading engine that populates `persona_performance`. |

**Cost model** (Plan.md §4 acceptance: < $5/day average):

- Haiku 4.5 universe screen (~500→top-30): ~$0.001/ticker × 4 personas × 50 tickers ≈ $0.20/day
- Sonnet 4.6 deep thesis (top-30 only): ~$0.012/thesis × 4 personas × 30 ≈ $1.44/day
- Persona spec cached (`cache_control: ephemeral`): saves ~3K tokens × 4 personas × ~5 calls ≈ ~$0.20/day saved
- Buffer for chat (Week 3): ~$1.00/day
- **Total: ~$2.50–4.00/day in steady-state.**

### Still mocked (as of 2026-06-12 evening — everything else is real)
- Dashboard "My portfolio" positions table + Social feed: Phase-D demo
  data (user accounts don't exist yet), labelled as such in the UI.
- User identity (no auth — assumes "jshin"). Phase D.
- Already swapped and deleted: `lib/mock/proposals.ts`, `lib/mock/reports.ts`,
  `lib/mock/chat.ts` (2026-06-05), **`lib/mock/performance.ts` (2026-06-12)** —
  charts/cards/leaderboard now read `/api/performance` + `/api/portfolio`.
  The 1y hypothetical backfill is flagged in the DB/API (`hypothetical`,
  migration 007); UI renders one solid line per persona with the caption
  "real fills since Jun 11, 2026" (product decision 2026-06-12 — no
  dashed split on screen). `lib/mock/personas.ts` remains as static
  character metadata (bios, accents, avgHold/turnover traits), not
  performance data.

### File map
```
apps/
  web/                              # Next.js 14 frontend (deployable to Vercel)
    app/
      layout.tsx                    # fonts, metadata
      page.tsx                      # landing / marketplace
      proposals/page.tsx            # by-analyst + consensus
      dashboard/page.tsx            # my portfolio + leaderboard + social
      how-it-works/page.tsx         # customer-facing explanation
      api/cron/daily/route.ts       # Vercel Cron entry (edge, Bearer-auth)
      api/cron/README.md            # cron env vars + manual test
      globals.css                   # Claude-design tokens
    components/                     # persona-card, persona-detail-sheet,
                                    # analyst-chat, report-list, header (with
                                    # inline mosaic mark), ui/*
    lib/mock/personas.ts            # static character metadata only —
                                    # bios, accents, traits (NOT perf data;
                                    # performance/proposals/reports/chat
                                    # mocks all deleted, now real /api/*)
    lib/analyst-data.ts             # fetchers: reports/proposals/features
    lib/performance-data.ts         # fetchers: performance/portfolio + hook
    public/personas/                # warren.jpg, cathie.jpg, ray.jpg, peter.jpg
    vercel.json                     # crons: daily "30 21 * * 1-5", weekly "0 22 * * 5"

  worker/                           # Python batch worker (Cloud Run-ready)
    pyproject.toml                  # pinned deps incl. anthropic, alpaca-py,
                                    # pandas, sqlalchemy, psycopg, pgvector
    tessera_worker/
      config.py                     # Pydantic Settings, env-var single source
      db.py                         # SQLAlchemy + psycopg3, session_scope()
      logging.py                    # structlog JSON; silences httpx/anthropic
                                    # loggers so API keys never leak
      main.py                       # FastAPI: /health, /jobs/* triggers
      universe.py                   # 51-ticker pilot universe with metadata
      ingestors/
        alpaca_eod.py               # equities + ETFs EOD bars
        coinbase_eod.py             # BTC/ETH daily candles (public API)
        fred_macro.py               # 37 macro series (yields, CPI, FX, oil, credit spreads, …)
        fmp_fundamentals.py         # income/balance/cashflow as jsonb
        newsapi_news.py             # ticker-tagged headlines + bodies
        sec_edgar.py                # 10-K + 10-Q filings → Neon + GCS
        sec_edgar_facts.py          # XBRL companyfacts → fundamentals (FMP gap)
        yf_shares.py                # yfinance synthetic row — shares /
                                    # mcap / peg / grossMargins / PE last-
                                    # resort fall-through (Phase C)
        yf_history.py               # yfinance Ticker.income_stmt — annual
                                    # EPS / revenue / GP per fy_end for
                                    # eps_cagr_3y + gross_margin_trend
                                    # (weekly cron, Friday only)
        fmp_key_metrics.py          # FMP /stable/key-metrics-ttm — daily-
                                    # current mcap + freeCashFlowYieldTTM /
                                    # peRatioTTM / etc. 5th mcap candidate
      features/
        compute.py                  # deterministic feature builder; per-
                                    # field newest-non-null walk +
                                    # cross_validated() helper; canonical
                                    # one-row-per-calendar-day OHLCV load
      agents/                       # Phase B — shipped
        persona_loader.py           # personalities.md → spec dicts
        prompt_assembler.py         # 6-part prompt + fetch_inputs(as_of)
        anthropic_runner.py         # typed calls, retry, cost log, persist
        citation_validator.py       # cited_news_ids must resolve
        models.py                   # re-exports tessera_shared schemas
        chat.py                     # SSE chat stream + 6-part system
        embeddings.py               # Voyage embed + pgvector literal
        ticker_resolver.py          # 6-level ticker resolution for chat
        persona_constraints.py      # construction-pass constraint registry
        portfolio_construction.py   # v2 pass-2: research → one book/persona
      risk/
        gateway.py                  # gate(report) + gate_regime(report) →
                                    # RiskCheckResult; universe + sum=1.0 +
                                    # single-name + sector caps (06-11) +
                                    # VaR99/drawdown-floor (06-12, #105)
        var.py                      # delta-normal VaR99 over calendar-
                                    # intersected log returns; MarketContext
                                    # loader; per-persona caps calibrated
                                    # against measured books (~2× headroom)
        attribution.py              # ticker-level P&L: qty_{d−1} × Δclose
                                    # over snapshots; contributions sum to
                                    # the period return (/api/attribution)
        paper_engine.py             # paper execution (shipped 2026-06-12,
                                    # FEATURE_PAPER_EXECUTION-gated): fill
                                    # latest book at next bar open → EOD
                                    # MTM → persona_performance; $100K
                                    # bootstrap; NAV conservation pinned;
                                    # failures page via explicit Sentry
                                    # capture (#108)
      jobs/
        ingest_daily.py             # 14-step orchestrator (what cron triggers);
                                    # advisory-locked against double-trigger
        backfill_history.py         # one-time deep-history pull
        persona_batch.py            # weekly Fri thesis batch (v2 two-pass)
        backtest_harness.py         # point-in-time replay → backtest_reports
        hallucination_canary.py     # post-batch invariant checks
        spy_canary.py               # nightly SPY 1y-return vs Yahoo guard
    scripts/
      check_connections.py          # smoke test all 6 services
      ingest_spy_canary.py          # acceptance test (0.49 bps vs Yahoo)
      run_universe_ingest_and_features.py  # end-to-end debug runner
      deploy_cloud_run.ps1          # build + deploy worker (Cloud Build → Run)
      inspect_ticker_features.py    # single-ticker fundamentals lineage
                                    # diagnostic (where did a value drop out?)
      inspect_v_rows.py             # recent payload fields per filing_type
      dump_v_xbrl_concepts.py       # every us-gaap concept a filer reports,
                                    # marking which our mapping covers
      dump_v_dei.py                 # peek at dei namespace coverage
      dump_v_income_recent.py       # merged income payload per period_end
                                    # (e.g. confirm yf_history fills FY rows)
      dump_nvda_cashflow.py         # recent cash_flow rows for one ticker
                                    # (used to diagnose null capex / FCF)
      dump_nvda_capex_obs.py        # per-XBRL-concept observations by form
                                    # /fy/fp; finds concept-name switches
    tests/                          # 19 files / 283 tests (2026-06-15)
      test_features.py              # feature math + hypothesis properties
      test_anthropic_runner.py      # parse/normalize/retry + as_of authority
      test_prompt_assembler.py      # incl. as_of leakage guards
      test_persona_loader.py        # personalities.md parsing
      test_persona_batch.py         # batch flow + budget handling
      test_chat.py                  # chat system assembly
      test_ticker_resolver.py       # 6-level resolution
      test_hallucination_canary.py  # 5 invariant checks
      test_main_api.py              # book aggregation, chat sanitize,
                                    # performance payload
      test_risk_gateway.py          # universe/sum/caps incl. sector
      test_paper_engine.py          # NAV conservation, sharpe/mdd math
      test_portfolio_construction.py # normalize_book invariants
      test_backfill_paper_history.py # ffill valuation + perf baseline
      test_ingestor_helpers.py      # yf symbol/NaN/label helpers

packages/
  shared/
    tessera_shared/schemas.py       # Pydantic contracts: AnalystReport,
                                    # Proposal, RegimeProbabilities, Portfolio,
                                    # Position, PersonaPerformance,
                                    # RiskCheckResult, ChatMessage, Persona

migrations/
  001_init.sql                      # v1 schema (Timescale + pgvector + 14 tables)
  002_persona_memory_vector_1024.sql  # pgvector dim bump for Voyage 3
  003_backtest_reports.sql          # backtest run history
  004_quality_features.sql          # PEG, mcap, EPS CAGR, D/E, GM, GM trend
  005_pe_ratios.sql                 # P/E trailing + forward (Phase C 06-09)
  006_ohlcv_canonical_day.sql       # one row per (ticker, calendar day) —
                                    # removes Alpaca-04:00Z / Yahoo-00:00Z
                                    # duplicates + orphaned feature rows;
                                    # re-run features + canary after apply
  007_hypothetical_track.sql        # hypothetical flag on the paper tables
                                    # (labels the frozen-book 1y backfill)
  008_cross_source_disagreements.sql  # mcap candidate-spread audit table (#125)
  009_llm_call_log_cost_namespace.sql # cost_namespace col → baseline ↔ prod
                                    # daily-cap isolation (#132)
  010_gross_margin_qtr_yoy.sql      # gross_margin_qtr_yoy_chg feature col (#133)
  011_fcf_yield_normalized.sql      # fcf_yield_normalized feature col (#134)
  012_users.sql                     # Phase D auth: ADD photo_url +
                                    # last_login_at to users (users +
                                    # user_portfolios already exist from
                                    # 001 §5); applied
  013_follow_events.sql             # follow/unfollow audit log for the
                                    # account curve; applied
  014_fcm_tokens.sql                # FCM web-push device tokens; pending apply

docs/                               # retros, ADRs, runbooks, Grafana JSON
build-deck.js                       # generates the Tessera deck (.pptx files
                                    # live in local-only decks/, gitignored)
```

---

## 7. Roadmap from here

| Phase | Scope | Status |
|---|---|---|
| **A. Live data wiring** | 5 ingestors + feature builder + universe + Vercel Cron + daily orchestrator | **✅ Done 2026-05-18** — see Phase A retro below |
| **B. Real LLM theses** (wk 2–3) | Wire `respond()` and report generation to Claude | **✅ Done 2026-06-05** — weekly v2 batch, live chat, reports/proposals UI |
| **C. Paper execution** (wk 4–5) | Persona positions executed in paper; daily P&L attribution | **✅ Done 2026-06-14** — gateway full (VaR99/DD/Ray), paper engine live (NAV-conserving + hit_rate FIFO closed-lot), integrity gates (point-in-time + stale-data + adjusted-price policy), performance/portfolio UI real, attribution endpoint + UI table, weight telemetry, Sentry paging, **90d backtest baseline (#132)** with `cost_namespace` isolation. Edge-case quant work shipped: fy_end_month FCF anchor (#121), FCF staleness guard (#128), gross_margin_qtr_yoy (#133), fcf_yield_normalized (#134). |
| **D. User auth + own portfolio** (wk 6) | Real user accounts following a persona on paper | 🟡 **Ready to start 2026-06-15** — Phase C carry-overs all closed (#132/#133/#134/#136). Scope: Firebase Auth + Google SSO, `users` table, follow CTA, `user_portfolios` + mirror engine, real dashboard positions, FCM push, onboard 3 F&F users. |
| **E. Compliance review** (wk 6, parallel) | Securities-lawyer consult before any non-self user runs live | ⏳ Blocked on Phase D scope — needs a concrete cohort + product description for the brief |
| **F. Live trading (optional)** (wk 7+) | Feature-flag flip; OAuth to user's Alpaca | ⏳ Blocked on E |

### Phase A retro (what shipped)

Built (real, in production against Neon):
- **Monorepo restructure** — apps/web + apps/worker + packages/shared + migrations
- **Neon Postgres** with TimescaleDB + pgvector — `001_init.sql` applied
- **Universe** — 51 tickers across sectors (49 equities + 2 crypto)
- **7 ingestors** — Alpaca EOD, Coinbase EOD, FRED macro (37 series), FMP fundamentals, NewsAPI, SEC EDGAR (10-K + 10-Q with GCS raw HTML), SEC XBRL companyfacts (structured fundamentals — fills FMP free-tier gap)
- **Feature builder** — ret_*, vol_30d, rsi_14, sma_{20,50}, volume_z; 13 property-based tests
- **Daily orchestrator** — `ingest_daily.py`, 8 steps, idempotent, CLI flags
- **Historical backfill job** (`backfill_history.py`, 2026-06-02) — one-shot operator script `--source {alpaca|coinbase|fred|yahoo|all}` that loaded 325K rows in 3 min: Alpaca 6yr, Coinbase 11yr, FRED full series-by-series history. yfinance opt-in via `[backfill]` extras for >7yr equity depth.
- **Vercel Cron** — `30 21 * * 1-5`, Bearer-auth endpoint
- **Sentry** — wired for both `tessera-web` and `tessera-worker` projects; errors-only (no perf traces / replays) for free-tier cost guard. Verified end-to-end with `/api/sentry-verify` (now removed). See `apps/web/sentry.*.config.ts` and `apps/worker/tessera_worker/observability.py`.
- **GCP + Cloud Run** (2026-06-01) — project `tessera-498200` (us-east1). Artifact Registry repo `tessera`. Service account `tessera-worker` with `roles/secretmanager.secretAccessor` + `roles/storage.objectAdmin` on `gs://tessera-raw`. Secret Manager holds 10 secrets (DATABASE_URL, ANTHROPIC, ALPACA × 2, FMP, FRED, NEWSAPI, SENTRY_DSN, WORKER_WEBHOOK_SECRET, SEC_USER_AGENT). Worker container deployed via `apps/worker/scripts/deploy_cloud_run.ps1` and verified end-to-end (Vercel cron call → ingest steps green).
- **SEC EDGAR ingestor** (2026-06-01) — adds `filings` step. Per ticker: 2 × 10-K + 4 × 10-Q (≈1.5 yrs of management prose). Body excerpt (8KB) into `filings.text_summary`, raw HTML to GCS `tessera-raw/edgar/{accession}.html`. Skip-if-already-have on accession means daily runs are no-ops once steady-state.
- **SEC XBRL companyfacts ingestor** (2026-06-02) — adds `edgar_facts` step. Pulls SEC's pre-parsed XBRL JSON (`/api/xbrl/companyfacts/CIK{cik}.json`), maps us-gaap concepts to FMP-compatible field names, JSONB-merges into `fundamentals` table. Coverage 39/42 tickers (vs FMP free 20/42); 3 missing for clear reasons (BRK.B ticker-dash, ASML+TSM foreign filers).

Verified:
- Connection check passes for all 6 external services
- SPY 1y return canary: **0.49 bps** vs Yahoo (threshold 100 bps)
- Full daily orchestrator: 6/6 steps green, ~8 min total (fundamentals dominates; 30-day cache afterwards)
- All 13 property tests pass

Deferred to Phase B:
- ~~Cloud Run worker deployment~~ — **shipped 2026-06-01** (see "Daily data flow" diagram above)
- ~~Sentry DSN registration~~ — **shipped 2026-06-01** (errors-only, cost-guarded)
- ~~SEC EDGAR filings ingestor~~ — **shipped 2026-06-01** (12 filings smoke-test for AAPL + MSFT, end-to-end Neon + GCS)
- ~~Frontend swap from `lib/mock/*` to `/api/*`~~ — **shipped** (reports/proposals/chat 2026-06-05; performance/portfolio 2026-06-12)

### Open questions to resolve before Phase B
- Decide if Cathie's universe should formally include crypto spot (BTC/ETH) or only equity proxies (COIN, MSTR).
- Whether to ship Manager-curated portfolios (Cons/Bal/Aggr) as a separate `/proposals` tab, or keep the current 4-portfolio side-by-side as the only view.
- Whether chat ("Chat with Warren") uses the same Sonnet calls as report generation (cheaper, slightly worse voice) or a fine-tuned Haiku per persona (more expensive to set up, much cheaper per call, stronger voice).

---

## 8. Cost (paper pilot, 3 users)

LLM dominates. Cost scales with batch frequency and persona count, not with users.

| Item | Monthly |
|---|---|
| LLM (Haiku 1st pass + Sonnet thesis, 4 personas, daily batch, caching on) | $60–280 |
| Cloud Run (free tier covers pilot) | $0–5 |
| Neon Postgres (free 0.5 GB) | $0 |
| Vercel Hobby + Firebase Spark | $0 |
| Market data (Alpaca free + FMP starter optional) | $0–30 |
| **Total** | **$60–315** |

One-time: securities-lawyer consult (~$300) before Phase E.

---

## 9. Hard rules we don't break

- **No custody.** Tessera never holds, moves, or receives user funds.
- **No live orders without explicit user approval.** Even after Phase F, every order requires user confirmation in the UI.
- **No personalized advice.** We publish ideas; we don't tell a specific user what to buy for their account.
- **No guarantees.** Marketing copy never implies promised returns. **Mechanically enforced** by `jobs/hallucination_canary.py` — every batch's `thesis_md` is grep'd for `"guaranteed return"`, `"can't lose"`, `"risk-free"`, `"insider tip"`, etc. Any hit = stop-the-world, Sentry alert, next batch skipped.
- **No hallucinated tickers.** Risk Gateway rejects anything not in the verified universe. **Mechanically enforced** at three layers: (1) `assemble_prompt` only emits tickers from `tessera_worker.universe`; (2) `citation_validator` drops invented `cited_news_ids` at runtime; (3) `hallucination_canary` re-verifies every persisted row's citations + side/conviction coherence + persona-topic-drift (Warren/Peter must not propose options).
- **No skipping paper.** Every persona, every strategy update, every new feature ships to paper first and runs for a meaningful window before any live exposure.
- **No mode-collapse to the cap.** `hallucination_canary` flags any `target_weight ≥ 0.19` (the 0.20 schema cap minus a 0.01 buffer) as a possible mode-collapse signal — see Plan §11 risk register. Detection is the trigger for the conviction-only-schema refactor (Plan §10 weight authority decision).

---

## 10. Versioning

| Version | Date | Notes |
|---|---|---|
| 0.1 | 2026-05-17 | Initial architecture: Vercel + Firebase + Cloud Run + Neon + Alpaca. PennyMaker brand. |
| 0.2 | 2026-05-18 | Renamed PennyMaker → Tessera. Reflects current frontend-MVP state (4 personas with photos and ages, chat feature, dedicated how-it-works route, paper-only scope). Roadmap split into 6 phases. |
| 0.3 | 2026-05-18 | Phase A complete. Monorepo (apps/web + apps/worker + packages/shared + migrations). Neon + Timescale + pgvector live. 5 ingestors (Alpaca, Coinbase, FRED, FMP, NewsAPI) + feature builder + daily orchestrator + Vercel Cron endpoint. 51-ticker universe. 13/13 property tests; SPY canary 0.49 bps vs Yahoo. File map and Phase A retro added; roadmap updated with status indicators. |
| 0.4 | 2026-06-11 | Codebase-audit sync (`docs/improvement-plan-2026-06-11.md`). Canonical-day note added (mixed-source OHLCV duplicates distorted production features; migration 006 + code dedup). File map refreshed to post-Phase-B reality (agents/ + jobs/ modules, 9 test files / 179 tests, migration 006). yfinance marked a core worker dependency (was a never-shipped optional extra). |
| 0.5 | 2026-06-12 | **Phase C core live.** Risk gateway (#94: universe/sum/single-name/sector caps inside construction retry loop) + PaperEngine v1 (#95/#96: fills at next bar open, EOD MTM, persona_performance, $100K bootstrap, `FEATURE_PAPER_EXECUTION=true`). §6 rewritten from "frontend-only demo" to current working-desk reality; roadmap B done / C in-progress; "Still mocked" trimmed to performance chart + auth. |
| 0.6 | 2026-06-12 | Step-4 doc close-out: file map refreshed (14 test files / 223 tests, migration 007, risk/paper_engine), LLM-pipeline section header no longer "in progress", performance mock removed from "Still mocked" (frontend swap #103 — only Phase-D account demos + auth remain), decks noted local-only. |
| 0.7 | 2026-06-12 | Risk/analytics layer (#105–#108): gateway gains VaR99 (risk/var.py, calibrated caps) + drawdown floor + Ray's gate_regime; risk/attribution.py + `/api/attribution`; canary weight telemetry; paper-engine Sentry paging. Roadmap C → "nearly done"; file map updated. |
| 0.8 | 2026-06-15 | **🏁 Phase C closed.** §5 acceptance 4/4 green: leaderboard real Sharpe/MDD per persona, cumulative chart = paper P&L sum, 90-day baseline (#132 `jobs/backtest_baseline.py`) per-archetype Sharpe (Warren 1.28 / Cathie 3.21 / Peter 2.81 / Ray 1.96), 0 risk-gate violations. Quant pass: fy_end_month FCF anchor (#121), `mcap_gap_yf_also_failed` coverage signal (#120), paper-engine integrity gates + adjusted-price policy (#122), hit_rate FIFO closed-lot tracking (#124), cross-source disagreements table + Grafana panel (#125), FCF staleness guard / CS-13 (#128), `cost_namespace` baseline ↔ prod cap isolation (#132), quarterly `gross_margin_qtr_yoy_chg` (#133), `fcf_yield_normalized` (#134), Cathie shortlist hotfix (#136). Migration 008–011 applied to prod. Roadmap C ✅ / D 🟡 ready. |
| 0.9 | 2026-06-15 | **Phase-D-ready deploy + post-deploy chaos fixes.** Docs synced to Phase-D-ready (#137). Three prod-deploy bugs surfaced and fixed: **CS-14** (#143) — `try_advisory_lock` now `conn.commit()`s after acquiring so the lock connection doesn't sit idle-in-transaction and get reaped by Neon mid-run (which had made the end-of-run `pg_advisory_unlock` throw → Job exit 1 on a 15-step green run); unlock also `suppress`-wrapped (#140). **CS-15** (#144) — `fcf_yield_normalized` populated only 1/59 tickers because `_load_fundamentals_latest`'s `cash_rows` omitted `form`/`fp` (EDGAR's annual marker; `period` is NULL there) and capped at 8 rows; fixed by adding form/fp to `cash_sql`+bucket and raising the cap 8→24, norm 1→38. Deploy script `-ImageTag` bare-tag footgun normalized + Jobs command echo (#139). §6 advisory-lock note updated. |
| 1.0 | 2026-06-16 | **Phase D kickoff — auth scaffolding.** `firebase` client SDK + `apps/web/lib/firebase/` (`client.ts` lazy/env-gated, `auth-context.tsx` `AuthProvider`/`useAuth`) wired into the root layout; header now does Google Sign-in / real user / Sign-out, falling back to the "jshin" pilot chip when `NEXT_PUBLIC_FIREBASE_*` is unset so prod never breaks pre-config. Migration `012_users.sql` (users keyed by `firebase_uid`, pending apply). Operator runbook `docs/runbooks/firebase-auth.md`. Server-side ID-token verification + `users` upsert deferred to the auth-sync PR. Also: mypy ledger 12→9 (agent trio burned); Slack cost-alert webhook marked live. |
| 1.7 | 2026-06-16 | **Email notifications (parallel to FCM).** `notify/email.py` emails a persona's followers (via `users.email`) on rebalance through Resend's HTTP API; `persona_batch._notify_followers` fires FCM + email independently (each isolated — one failing never blocks the other or the batch). Email is the channel web push can't reach (iOS without PWA, opt-outs). `build_email` is pure + unit-tested. Gated on `FEATURE_EMAIL_NOTIFY` + `RESEND_API_KEY` (+ `EMAIL_FROM`); ships dark. Runbook firebase-auth.md §6. |
| 1.6 | 2026-06-16 | **FCM push on rebalance (dark).** Web "Enable notifications" toggle → `getToken(VAPID)` → `/api/me/fcm-token` (`fcm_tokens`, migration 014) + `public/firebase-messaging-sw.js` background handler. Worker `notify/fcm.py` pushes a persona's followers from `persona_batch` after a new book persists (best-effort — never breaks the batch). **Keyless send**: the worker SA's OAuth token comes from the Cloud Run metadata server (cloud-platform scope) → FCM HTTP v1; setup is one cross-project IAM binding (`roles/firebasecloudmessaging.admin` on `tessera-641a5`), no SA key (CS-9). Gated on `FEATURE_FCM_PUSH` + the VAPID env; ships dark. Runbook firebase-auth.md §5. |
| 1.5 | 2026-06-16 | **Account curve across follow history.** `follow_events` (migration 013) logs every follow/unfollow (best-effort write from `/api/follow` — never fails the follow, survives 013 not-yet-applied); `GET /api/me/timeline` returns them; `lib/account-curve.ts` reconstructs the user's whole paper account over the full ~1y S&P window — flat (grey) in cash, compounding the mean daily return of followed personas while followed, cut into colour-coded segments at every follow/unfollow. The dashboard chart now ALWAYS draws S&P 500 over the full window (fixes the blank-chart-on-fresh-follow regression) and overlays the segmented account line. |
| 1.4 | 2026-06-16 | **Dashboard wired to real follows.** `GET /api/me/portfolios` (Edge, token-verified) reads `user_portfolios`; the `/dashboard` "My portfolio" tab renders real follows — multi-follow persona selector, curve rebased to the follow date, positions table, tiles, sign-in / no-follows empty states. The hardcoded `peter` mock is deleted; only the Social tab remains a labelled Phase-D demo. Personal P&L ("% since follow") falls out of the mirror engine. Phase D UI is now end-to-end real (auth → follow → mirror → dashboard); remaining: FCM push + F&F onboarding. |
| 1.3 | 2026-06-16 | **Mirror engine.** New nightly `mirror` ingest step (`risk/mirror.py`, after `paper`, same `FEATURE_PAPER_EXECUTION` gate) projects each persona's paper book onto its followers' `user_portfolios` by weight: `follower_nav = starting_capital × (persona_nav_today / persona_nav_at_follow_start)`, holdings = persona's current weights scaled to that NAV. Deterministic (no per-follower fill sim), `started_at`-anchored (no look-ahead). `project_follower_book` is a pure, unit-tested helper (5 tests). `user_portfolios` positions/cash/total_value are now real; the `/dashboard` frontend swap (still mock) is the remaining Phase-D UI piece. |
| 1.2 | 2026-06-16 | **Follow a persona.** `FollowButton` on the persona detail sheet + `/api/follow` (Edge: GET status / POST seed / DELETE). A follow seeds the user's $100K paper `user_portfolios` row (the row IS the follow — no separate `follows` table; user_portfolios predates this from 001 §5); unfollow drops it. User derived from the verified Firebase token only. Mirror engine (populating follower positions when a persona rebalances) + dashboard real positions are next. |
| 1.1 | 2026-06-16 | **Auth-sync — login persists a user (Phase D auth live).** `/api/auth/sync` (Edge) verifies the Firebase ID token with `jose` against Google's public JWKS — no firebase-admin / service-account secret, only the public project id — then upserts the `users` row via `@neondatabase/serverless`. **New architectural boundary:** the web app now writes the USER layer (users; later user_portfolios / follows) **directly to Neon**, while the worker keeps owning the market-data plane (UI still reads personas/performance through worker HTTP). Migration 012 applied to prod (additive ALTER; users predated it from 001 §5 — CS-16). Needs `DATABASE_URL` on Vercel. Firebase project `tessera-641a5` live with Google SSO. |

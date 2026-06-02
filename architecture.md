# Tessera Architecture

> An agentic research desk. Four AI analyst personas with distinct philosophies
> each publish a long-term portfolio side-by-side. Paper-trading MVP today,
> live-execution ready by design.

---

## 1. Product overview

| | |
|---|---|
| **Brand** | Tessera ("a small tile in a mosaic" — each analyst is a piece of the whole) |
| **Stage** | Frontend MVP (mock data, no backend). Paper-trading pilot to follow. |
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

## 6. Current MVP (what is actually built)

The codebase right now is a **frontend-only demo** with mock data — no backend,
no broker, no LLM. It exists to validate UX before backend investment.

### Frontend MVP (shipped, 4 routes on Vercel)
- **Marketplace** (`/`) — landing page = persona grid; click any card opens a slide-over detail sheet. Header logo is an inline SVG mosaic mark (coral / ink / sage tiles).
- **Persona detail sheet** — biography, signature signals, full 1-year performance chart vs S&P 500, recent reports (accordion), latest portfolio, and a Chat toggle.
- **Chat with analyst** — UI complete; mock response engine in `lib/mock/chat.ts` uses keyword matching against persona-specific response banks. Streams character-by-character to feel real. No LLM calls *yet* (Phase B will swap to Anthropic).
- **Proposals** (`/proposals`) — two tabs: "By analyst" (4 portfolios side-by-side) and "Consensus" (cross-analyst agreement table).
- **Dashboard** (`/dashboard`) — user account view with tabs: My portfolio, Leaderboard, Social feed. URL-synced (`?tab=…`).
- **How it works** (`/how-it-works`) — customer-facing explanation of pipeline, safety, and compliance posture.
- **Vercel Cron endpoint** (`/api/cron/daily`) — edge runtime, Bearer-auth via `CRON_SECRET`, scheduled `30 21 * * 1-5` in `vercel.json`. Returns `{status: "noop"}` until `WORKER_WEBHOOK_URL` is wired.

### Phase A backend (shipped, runs against production Neon)
- **Neon Postgres** provisioned (us-east-1, free tier), `001_init.sql` applied. 14 tables + 3 extensions (TimescaleDB, pgvector, uuid-ossp).
- **Python worker** (apps/worker) with FastAPI skeleton, structured JSON logging, SQLAlchemy + psycopg3 session pool.
- **5 ingestors operational**: Alpaca EOD (equities + ETFs), Coinbase EOD (BTC, ETH), FMP fundamentals (`/stable/` endpoints), FRED macro (20 series), NewsAPI (ticker-tagged headlines). All idempotent via `ON CONFLICT DO UPDATE`.
- **Universe**: 51 tickers (49 equities + 2 crypto pairs) spanning the sectors each persona cares about.
- **Feature builder** (`compute.py`): deterministic pandas/numpy module. Reads `ohlcv_1d`, writes `ticker_features`. Computes ret_{1d,5d,30d,90d,1y}, vol_30d, rsi_14, sma_{20,50}, volume_z. **This is the only path numerical features reach the LLM** (Phase B). 13 property-based tests on the math.
- **Daily orchestrator** (`jobs/ingest_daily.py`): 6 sequential steps (ohlcv_equity → ohlcv_crypto → macro → fundamentals → news → features). CLI flags `--only`/`--skip`. Exit code 0/1 maps to Cloud Run Job success/failure.
- **Connection smoke test** (`scripts/check_connections.py`): verifies all 6 external services + redacts secrets from any error output.
- **Production state right now** (snapshot 2026-06-01, after first Cloud Run-driven run):
  - `ohlcv_1d`: ~14,600 rows (53 tickers × ~270 trading days)
  - `ticker_features`: ~14,500 rows
  - `macro_series`: ~650 rows from 20 FRED series
  - `fundamentals`: ~300 rows (FMP free tier blocks some premium endpoints; `fmp.fetch_skip` logs are expected)
  - `news`: ~1,650 rows tagged to 42 tickers
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
│        ↓ 6 sequential steps, each idempotent                │
│        1. Alpaca EOD     → ohlcv_1d (equities)              │
│        2. Coinbase EOD   → ohlcv_1d (crypto)                │
│        3. FRED macro     → macro_series                     │
│        4. FMP fundamentals (30-day cache) → fundamentals    │
│        5. NewsAPI        → news                             │
│        6. Feature builder → ticker_features                 │
│        ↓ UPSERT (ON CONFLICT DO UPDATE)                     │
│  Neon Postgres   (single source of truth for all data)      │
│        ↓ stdout (structlog JSON)                            │
│  GCP Logging  +  Sentry (errors only)                       │
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

**Data lives only in Neon.** Cloud Run is stateless — when a job finishes the worker memory is freed and the container may scale to zero. Local `.env` files hold API keys but no data. To onboard a new dev: `git clone` + `.env` from 1Password + `pip install -e .` is enough to run the same code against the same Neon DB.

**Concurrent-run note (Phase C todo)**: there is no app-level lock today. If two trigger calls land within the same second (e.g., manual curl + scheduled cron), both ingests run in parallel. Steps are idempotent so the DB stays consistent, but rare `step_failed` events can show up in logs from row-level conflicts. Phase C will add an advisory lock (`pg_advisory_lock(hashtext('ingest_daily'))`) so the second trigger is a fast no-op.

### External data sources (what we ingest, what it costs, why)

| Source | Auth | Cost | What we pull | Cadence | Destination table |
|---|---|---|---|---|---|
| **Alpaca** | API key + secret | Free (IEX feed only) | EOD OHLCV for 49 US equities + ETFs | Daily, last 30d window | `ohlcv_1d` (source='alpaca') |
| **Coinbase Exchange** | None — public API | Free, unmetered | BTC-USD, ETH-USD daily candles | Daily, last 30d | `ohlcv_1d` (source='coinbase') |
| **FRED** (St. Louis Fed) | API key | Free, unmetered | 20 macro series (yields, CPI, unemployment, M2, VIX, USD …) | Daily, last 90d | `macro_series` |
| **FMP** (Financial Modeling Prep) | API key | Free tier (some premium endpoints 402) | Annual income / balance / cashflow as JSON | 30-day cache per ticker | `fundamentals` |
| **NewsAPI** | API key | Free tier (100 req/day) | Ticker-tagged headlines + body excerpts | Daily, last 24h | `news` |
| **SEC EDGAR** | `User-Agent` header (name + contact email) | Free, unmetered | 10-K (annual) + 10-Q (quarterly) full filings | Weekly (skip if accession already stored) | `filings` (meta + 8KB excerpt) + GCS (raw HTML) |

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
| Yahoo Finance scrape | No stable API, ToS-grey area, anti-bot defenses |
| Polygon.io | Better data but paid ($30+/mo) — Alpaca free covers Phase A/B needs |
| IEX Cloud | Sunsetting in 2024 |

### How to read the data we've stored

Six tables matter for downstream work (LLM, frontend, ad-hoc analysis):

```
ohlcv_1d           # prices (Timescale hypertable)
macro_series       # FRED series
fundamentals       # FMP, JSON blobs per period
news               # NewsAPI, embedding column ready for pgvector
filings            # SEC EDGAR (excerpt + GCS pointer)
ticker_features    # derived: ret_*, vol_30d, rsi_14, sma_*, volume_z
```

**Three access patterns:**

#### 1. Direct SQL — fastest for exploration
Connect with the `DATABASE_URL` from 1Password (same DB everyone uses). From `psql`, DBeaver, Neon's web console, or any Postgres client:

```sql
-- Apple's last 5 trading days
SELECT ts, close, volume FROM ohlcv_1d
WHERE ticker = 'AAPL'
ORDER BY ts DESC LIMIT 5;

-- Latest features for the whole universe (one row per ticker)
SELECT DISTINCT ON (ticker) ticker, ts, ret_30d, rsi_14, vol_30d
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

#### 3. HTTP API from the frontend — Phase B onwards
Right now the Next.js app reads `lib/mock/*` (seeded fakes). Phase B Week 3 swaps these for real `/api/*` routes that query Neon server-side. The frontend never touches Neon directly; everything goes through Vercel edge routes that hold the DB credential.

Sketch of the route shape (not yet implemented):

```
GET /api/performance?personaId=warren&window=30d
  → returns equity-curve points from persona_performance

GET /api/reports?personaId=warren&limit=5
  → returns analyst_reports rows for one persona

GET /api/proposals?ticker=NVDA
  → returns latest proposal per persona (1..4 rows)

POST /api/chat/[personaId]
  → SSE stream from Anthropic Sonnet, with persona spec +
    book + recent reports + relevant features injected as
    system prompt context
```

The web app's `lib/api.ts` will wrap these calls so components stay agnostic to mock-vs-real.

**Connection cheatsheet** — credentials always come from secrets store, never code:

| Caller | Where DATABASE_URL lives | How |
|---|---|---|
| Local Python (you running ingest) | `apps/worker/.env` | `python-dotenv` auto-loads on import |
| Cloud Run worker | GCP Secret Manager | `gcloud run deploy --set-secrets` mounts as env var |
| Local Next.js (npm run dev) | `apps/web/.env.local` | Next.js auto-loads `.env.local` |
| Vercel production | Vercel project env vars | Set in dashboard → Settings → Environment Variables |

### Still mocked (Frontend reads these — Phase B/C swap)
- All return series (seeded random walks in `lib/mock/performance.ts`).
- All proposals (hand-curated in `lib/mock/proposals.ts`).
- All reports (hand-written in `lib/mock/reports.ts`).
- Chat responses (keyword bank in `lib/mock/chat.ts`).
- User identity (no auth — assumes "jshin").

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
    lib/mock/                       # personas, performance, proposals,
                                    # reports, chat (Phase B replaces)
    public/personas/                # warren.jpg, cathie.jpg, ray.jpg, peter.jpg
    vercel.json                     # cron schedule "30 21 * * 1-5"

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
        fred_macro.py               # 20 macro series (yields, CPI, etc.)
        fmp_fundamentals.py         # income/balance/cashflow as jsonb
        newsapi_news.py             # ticker-tagged headlines + bodies
      features/
        compute.py                  # deterministic feature builder
      agents/                       # (Phase B — empty)
      risk/                         # (Phase C — empty)
      jobs/
        ingest_daily.py             # 6-step orchestrator (what cron triggers)
    scripts/
      check_connections.py          # smoke test all 6 services
      ingest_spy_canary.py          # acceptance test (0.49 bps vs Yahoo)
      run_universe_ingest_and_features.py  # end-to-end debug runner
    tests/
      test_features.py              # 13 hypothesis property tests

packages/
  shared/
    tessera_shared/schemas.py       # Pydantic contracts: AnalystReport,
                                    # Proposal, RegimeProbabilities, Portfolio,
                                    # Position, PersonaPerformance,
                                    # RiskCheckResult, ChatMessage, Persona

migrations/
  001_init.sql                      # v1 schema (Timescale + pgvector + 14 tables)

docs/                               # phase retros (Phase B-onwards)
build-deck.js                       # generates tessera-deck.pptx
```

---

## 7. Roadmap from here

| Phase | Scope | Status |
|---|---|---|
| **A. Live data wiring** | 5 ingestors + feature builder + universe + Vercel Cron + daily orchestrator | **✅ Done** — see Phase A retro below |
| **B. Real LLM theses** (wk 2–3) | Wire `respond()` and report generation to Claude | ⏳ Next — data plane ready |
| **C. Paper execution** (wk 4–5) | Persona positions executed in paper; daily P&L attribution | ⏳ Planned |
| **D. User auth + own portfolio** (wk 6) | Real user accounts following a persona on paper | ⏳ Planned |
| **E. Compliance review** (wk 6, parallel) | Securities-lawyer consult before any non-self user runs live | ⏳ Planned |
| **F. Live trading (optional)** (wk 7+) | Feature-flag flip; OAuth to user's Alpaca | ⏳ Optional |

### Phase A retro (what shipped)

Built (real, in production against Neon):
- **Monorepo restructure** — apps/web + apps/worker + packages/shared + migrations
- **Neon Postgres** with TimescaleDB + pgvector — `001_init.sql` applied
- **Universe** — 51 tickers across sectors (49 equities + 2 crypto)
- **5 ingestors** — Alpaca EOD, Coinbase EOD, FRED macro, FMP fundamentals, NewsAPI
- **Feature builder** — ret_*, vol_30d, rsi_14, sma_{20,50}, volume_z; 13 property-based tests
- **Daily orchestrator** — `ingest_daily.py`, 6 steps, idempotent, CLI flags
- **Vercel Cron** — `30 21 * * 1-5`, Bearer-auth endpoint
- **Sentry** — wired for both `tessera-web` and `tessera-worker` projects; errors-only (no perf traces / replays) for free-tier cost guard. Verified end-to-end with `/api/sentry-verify` (now removed). See `apps/web/sentry.*.config.ts` and `apps/worker/tessera_worker/observability.py`.
- **GCP + Cloud Run** (2026-06-01) — project `tessera-498200` (us-east1). Artifact Registry repo `tessera`. Service account `tessera-worker` with `roles/secretmanager.secretAccessor`. Secret Manager holds 9 secrets (DATABASE_URL, ANTHROPIC, ALPACA × 2, FMP, FRED, NEWSAPI, SENTRY_DSN, WORKER_WEBHOOK_SECRET). Worker container deployed via `apps/worker/scripts/deploy_cloud_run.ps1` and verified end-to-end (Vercel cron call → 6/6 ingest steps green).

Verified:
- Connection check passes for all 6 external services
- SPY 1y return canary: **0.49 bps** vs Yahoo (threshold 100 bps)
- Full daily orchestrator: 6/6 steps green, ~8 min total (fundamentals dominates; 30-day cache afterwards)
- All 13 property tests pass

Deferred to Phase B:
- ~~Cloud Run worker deployment~~ — **shipped 2026-06-01** (see "Daily data flow" diagram above)
- ~~Sentry DSN registration~~ — **shipped 2026-06-01** (errors-only, cost-guarded)
- SEC EDGAR filings ingestor (Phase B Week 2 — `filings` schema exists, not yet populated)
- Frontend swap from `lib/mock/*` to `/api/*` (Phase B Week 3 — sequence: real theses must exist first)

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
- **No guarantees.** Marketing copy never implies promised returns.
- **No hallucinated tickers.** Risk Gateway rejects anything not in the verified universe.
- **No skipping paper.** Every persona, every strategy update, every new feature ships to paper first and runs for a meaningful window before any live exposure.

---

## 10. Versioning

| Version | Date | Notes |
|---|---|---|
| 0.1 | 2026-05-17 | Initial architecture: Vercel + Firebase + Cloud Run + Neon + Alpaca. PennyMaker brand. |
| 0.2 | 2026-05-18 | Renamed PennyMaker → Tessera. Reflects current frontend-MVP state (4 personas with photos and ages, chat feature, dedicated how-it-works route, paper-only scope). Roadmap split into 6 phases. |
| 0.3 | 2026-05-18 | Phase A complete. Monorepo (apps/web + apps/worker + packages/shared + migrations). Neon + Timescale + pgvector live. 5 ingestors (Alpaca, Coinbase, FRED, FMP, NewsAPI) + feature builder + daily orchestrator + Vercel Cron endpoint. 51-ticker universe. 13/13 property tests; SPY canary 0.49 bps vs Yahoo. File map and Phase A retro added; roadmap updated with status indicators. |

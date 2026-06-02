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
- **6 production ingestors**: Alpaca EOD, Coinbase EOD, FRED macro, FMP fundamentals, NewsAPI, SEC EDGAR (10-K + 10-Q with GCS raw HTML)
- **51-ticker universe** spanning sectors each persona cares about
- **Deterministic feature builder** — ret_*, vol_30d, rsi_14, sma_{20,50}, volume_z. 13/13 hypothesis tests pass.
- **Daily orchestrator** (`ingest_daily.py`) — 7 sequential steps, idempotent, CLI flags
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

### Week 2 Quickstart — working with the data we already have

Phase A wired the entire data plane. **Quant (예슬, 준원) and LLM Pipeline (윤채, 한솔) work on top of what's already there** — nobody needs to wait on infra.

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

Local GCS access requires `gcloud auth application-default login` once.

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

#### Worked example A (LLM Pipeline) — assemble Warren's AAPL thesis input end-to-end

The single most useful snippet to internalize. Save as `apps/worker/scripts/_warren_aapl_demo.py`, then `python -m scripts._warren_aapl_demo`. This is what the real `prompt_assembler.py` will do programmatically for all 4 personas × ~30 shortlisted tickers daily.

```python
"""Demo: gather every input Warren's prompt would need for AAPL.
Run from apps/worker/ with the venv active."""
from datetime import date, timedelta
from sqlalchemy import text
from tessera_worker.db import session_scope

TICKER = "AAPL"
LOOKBACK_NEWS_DAYS = 7

with session_scope() as session:
    # ─── 1. Price + return snapshot (latest row in ticker_features) ───
    feat = session.execute(text("""
        SELECT ts, ret_1d, ret_5d, ret_30d, ret_90d, ret_1y,
               vol_30d, rsi_14, sma_20, sma_50, volume_z
        FROM ticker_features WHERE ticker = :t
        ORDER BY ts DESC LIMIT 1
    """), {"t": TICKER}).mappings().first()

    # ─── 2. Last 30 days of closes (for chart context in the prompt) ───
    prices = session.execute(text("""
        SELECT ts, close FROM ohlcv_1d
        WHERE ticker = :t ORDER BY ts DESC LIMIT 30
    """), {"t": TICKER}).all()

    # ─── 3. Latest annual fundamentals (what Warren actually values) ───
    fund = session.execute(text("""
        SELECT period, income_stmt, balance_sheet, cash_flow
        FROM fundamentals
        WHERE ticker = :t AND period_type = 'annual'
        ORDER BY period DESC LIMIT 1
    """), {"t": TICKER}).mappings().first()

    # ─── 4. Macro backdrop (Warren cares about real rates + credit spread) ───
    macros = session.execute(text("""
        SELECT series_id, value FROM macro_series
        WHERE series_id = ANY(:ids)
          AND ts = (SELECT MAX(ts) FROM macro_series WHERE series_id='DGS10')
    """), {"ids": ["DGS10", "T10YIE", "BAMLH0A0HYM2"]}).all()

    # ─── 5. Recent news headlines (Warren wants signal, not noise — 7 days) ───
    news = session.execute(text("""
        SELECT ts, source, title, id FROM news
        WHERE :t = ANY(tickers)
          AND ts >= :since
        ORDER BY ts DESC LIMIT 10
    """), {"t": TICKER, "since": date.today() - timedelta(days=LOOKBACK_NEWS_DAYS)}).all()

    # ─── 6. Latest 10-K excerpt (Warren reads management's prose carefully) ───
    filing = session.execute(text("""
        SELECT filing_date, period_end, text_summary, raw_gcs_uri
        FROM filings
        WHERE ticker = :t AND filing_type = '10-K'
        ORDER BY filing_date DESC LIMIT 1
    """), {"t": TICKER}).mappings().first()

# ─── Print what we got — this is the raw material the prompt assembler bundles ───
print(f"=== {TICKER} snapshot as of {feat['ts']} ===")
print(f"Returns: 1d={feat['ret_1d']:+.2%}  30d={feat['ret_30d']:+.2%}  1y={feat['ret_1y']:+.2%}")
print(f"Vol30={feat['vol_30d']:.2%}  RSI14={feat['rsi_14']:.0f}  SMA20={feat['sma_20']:.2f}")
print()
print(f"Macro context: " + ", ".join(f"{r.series_id}={r.value}" for r in macros))
print()
print(f"Last {len(news)} news (7d):")
for n in news:
    print(f"  {n.ts.date()}  [{n.source}]  {n.title[:80]}")
print()
print(f"Latest 10-K: filed {filing['filing_date']}, period_end {filing['period_end']}")
print(f"  Excerpt ({len(filing['text_summary']):,} chars):")
print(f"  {filing['text_summary'][:400]}…")
print(f"  Full HTML at {filing['raw_gcs_uri']}")
```

**What each of the 6 blocks becomes in the actual prompt** (LLM Pipeline pattern reference):

| Block | Where it lands in the system prompt |
|---|---|
| 1. Feature snapshot | `<features>` block — numbers Warren can quote as evidence |
| 2. Price history | Used by Quant for chart sparkline in the UI; LLM gets only the summary stats |
| 3. Fundamentals JSON | `<financials>` block — Warren computes FCF yield, P/E from this |
| 4. Macro | `<context>` block — sets the regime Warren is operating in |
| 5. News | `<news>` block — each item has `id` so Warren must cite by ID (citation validator enforces) |
| 6. 10-K excerpt | `<filing>` block — direct quotes from management; this is where Warren picks up qualitative signal that pure numbers miss |

**Persona-specific tweaks** the real assembler will apply:

- **Warren**: include 10-K excerpt (block 6) at full length, downweight macros, include 5y EPS history from `fundamentals`.
- **Cathie**: skip 10-K (she invests on disruption narrative), include heavy news (block 5) and `volume_z`/`ret_30d` momentum.
- **Ray**: skip filings + news for individual tickers, include ALL macro series (yield curve, breakevens, VIX, USD), aggregate per-asset-class signals.
- **Peter**: include both filings and PEG-relevant fundamentals; news only if `ret_30d > 10%` (his "is the market noticing yet?" filter).

That selectivity is exactly what `prompt_assembler.py` per-persona logic encodes — same data sources, different cut.

#### Worked example B (Quant) — compute FCF yield + screen the universe end-to-end

The Quant equivalent of the Warren+AAPL demo. Save as `apps/worker/scripts/_fcf_yield_demo.py`, then `python -m scripts._fcf_yield_demo`. Shows the read → compute → upsert pattern that every new feature in `features/compute.py` will follow.

```python
"""Demo: compute FCF yield for the equity universe, rank it,
write back to ticker_features. Run from apps/worker/ with venv active.

FCF yield = trailing free cash flow / market cap
  free cash flow         ← fundamentals.cash_flow JSONB
  market cap = price × shares outstanding
                          ← ohlcv_1d.close (latest) × fundamentals.balance_sheet (latest)
"""
import json
import pandas as pd
from sqlalchemy import text
from tessera_worker.db import session_scope
from tessera_worker.universe import by_asset_class

tickers = [t.ticker for t in by_asset_class("equity")]  # 49 names

with session_scope() as session:
    # ─── 1. Latest close per ticker (Timescale handles "latest" fast) ───
    closes = session.execute(text("""
        SELECT DISTINCT ON (ticker) ticker, close
        FROM ohlcv_1d
        WHERE ticker = ANY(:t)
        ORDER BY ticker, ts DESC
    """), {"t": tickers}).all()
    close_by = {r.ticker: float(r.close) for r in closes}

    # ─── 2. Latest annual fundamentals per ticker (JSONB extraction) ───
    funds = session.execute(text("""
        SELECT DISTINCT ON (ticker) ticker,
               cash_flow ->> 'freeCashFlow'             AS fcf,
               balance_sheet ->> 'commonStockShares'    AS shares
        FROM fundamentals
        WHERE ticker = ANY(:t) AND period_type = 'annual'
        ORDER BY ticker, period DESC
    """), {"t": tickers}).all()

# ─── 3. Compute in pandas (deterministic, easy to property-test) ───
rows = []
for r in funds:
    fcf, shares = r.fcf, r.shares
    if not fcf or not shares: continue
    fcf, shares = float(fcf), float(shares)
    close = close_by.get(r.ticker)
    if not close: continue
    market_cap = close * shares
    if market_cap <= 0: continue
    rows.append({"ticker": r.ticker, "fcf_yield": fcf / market_cap})

df = pd.DataFrame(rows).sort_values("fcf_yield", ascending=False)

# ─── 4. Show the screen — top 10 cheapest by FCF yield ───
print("=== FCF yield screen (top 10) ===")
print(df.head(10).to_string(index=False, float_format=lambda v: f"{v:.2%}"))

# ─── 5. Write back into ticker_features as a new column.
#    In the real `features/compute.py`, you'd add this to the build()
#    function so it goes through the existing upsert path. This demo
#    shows the SQL for it explicitly:
WRITE_BACK = False  # flip to True after schema migration adds fcf_yield col
if WRITE_BACK:
    with session_scope() as session:
        session.execute(text("""
            UPDATE ticker_features SET fcf_yield = :fcf_yield
            WHERE ticker = :ticker
              AND ts = (SELECT MAX(ts) FROM ticker_features WHERE ticker = :ticker)
        """), df.to_dict(orient="records"))
```

**The Quant pattern this demonstrates** (apply to every new feature you add):

| Step | What you do | Where it lives |
|---|---|---|
| 1. Identify inputs | Which existing tables hold the raw signal? | Read `architecture.md` §6 schema list |
| 2. Read minimally | Use `DISTINCT ON (ticker)` for "latest per ticker" so you don't drag full history | Right at the top of the function |
| 3. Compute in pandas | Pure function, no DB calls during the math | `features/compute.py` |
| 4. Property test | One `hypothesis` test that proves the math holds on synthetic data | `tests/test_features.py` |
| 5. Schema migrate | If adding a column, write `migrations/00X_add_<feature>.sql` and ADR if non-trivial | `migrations/` |
| 6. Wire to upsert | Plug the function into the existing `build()` pipeline so daily cron picks it up | `features/compute.py` `build()` |

**Phase B feature backlog for Quant** (`features/compute.py` extensions, in priority order):

1. **`fcf_yield`** — Warren's primary screen. Pattern shown above.
2. **`peg_ratio`** — Peter's screen. Needs forward EPS estimate (use FMP `analyst_estimates` if accessible, else trailing as proxy).
3. **`eps_cagr_3y`** — both Warren and Peter want growth durability. Compute from 3 consecutive annual `fundamentals.income_stmt`.
4. **`debt_to_equity`** — risk hygiene for every persona. `fundamentals.balance_sheet`.
5. **`gross_margin_trend`** — Cathie's "is it scaling?" signal. 4 quarters of `fundamentals.income_stmt`.
6. **`news_sentiment_30d`** — placeholder for Phase C; need an LLM or local model to score `news.body`.

**Phase C precursor work** (start sketching now, ship next phase):

- **Correlation matrix** of equity universe (rolling 90d) → goes into risk gateway's "diversification floor" check.
- **Sector exposure tagging** from `universe.py` metadata × per-persona portfolio weights → used by risk gateway's "single-sector cap" check.

These two are read-only (don't write back to `ticker_features`) — they're called on demand by the risk gateway in Phase C Week 4.

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

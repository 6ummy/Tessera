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

### What works
- **Marketplace** (`/`) — landing page = persona grid; click any card opens a slide-over detail sheet.
- **Persona detail sheet** — biography, signature signals, full 1-year performance chart vs S&P 500, recent reports (accordion), latest portfolio, and a Chat toggle.
- **Chat with analyst** — UI complete; mock response engine in `lib/mock/chat.ts` uses keyword matching against persona-specific response banks. Streams character-by-character to feel real. No LLM calls.
- **Proposals** (`/proposals`) — two tabs: "By analyst" (4 portfolios side-by-side) and "Consensus" (cross-analyst agreement table).
- **Dashboard** (`/dashboard`) — user account view with tabs: My portfolio, Leaderboard, Social feed. URL-synced (`?tab=…`).
- **How it works** (`/how-it-works`) — customer-facing explanation of pipeline, safety, and compliance posture.
- **Header user menu** — dropdown to Dashboard / Leaderboard / Social.

### What is mocked
- All return series (seeded random walks in `lib/mock/performance.ts`).
- All proposals (hand-curated in `lib/mock/proposals.ts`).
- All reports (hand-written in `lib/mock/reports.ts`).
- Chat responses (keyword bank in `lib/mock/chat.ts`).
- User identity (no auth — assumes "jshin").

### File map
```
app/
  layout.tsx               # fonts, metadata
  page.tsx                 # landing / marketplace
  proposals/page.tsx       # by-analyst + consensus
  dashboard/page.tsx       # my portfolio + leaderboard + social
  how-it-works/page.tsx    # customer-facing explanation
  globals.css              # Claude-design tokens

components/
  header.tsx               # sticky nav + user menu
  persona-card.tsx         # marketplace card
  persona-avatar.tsx       # photo with letter-fallback
  persona-detail-sheet.tsx # slide-over with Thesis/Chat toggle
  analyst-chat.tsx         # streaming chat UI
  report-list.tsx          # accordion of analyst reports
  cumulative-chart.tsx     # Recharts wrapper
  sparkline.tsx
  ui/ { button, badge, sheet, tabs }

lib/
  utils.ts                 # cn, fmt, signClass
  mock/
    personas.ts            # 4 personas with age, photo, metrics
    performance.ts         # seeded random-walk return series
    proposals.ts           # current holdings per persona + consensus
    reports.ts             # 2 written reports per persona
    chat.ts                # keyword-matched response engine

public/personas/           # warren.jpg, cathie.jpg, ray.jpg, peter.jpg
```

---

## 7. Roadmap from here

| Phase | Scope | Key adds |
|---|---|---|
| **A. Live data wiring** (now → 4 wks) | Replace mock data with real EOD + computed features | Neon schema, Alpaca/FMP/FRED ingestors, Python feature builder, Cloud Run scheduler |
| **B. Real LLM theses** (wks 4–6) | Wire `respond()` and report generation to Claude | Anthropic SDK calls, prompt caching, Pydantic validators, citation verification |
| **C. Paper execution** (wks 6–10) | Persona positions executed in paper; daily P&L attribution | Paper engine, ledger schema, mark-to-market, persona_performance computation |
| **D. User auth + own portfolio** (wks 10–12) | Real user accounts following a persona on paper | Firebase Auth, Firestore portfolio_selections, push alerts on rebalance |
| **E. Compliance review** (before live trading) | Securities-lawyer consult before any non-self user runs live | RIA exemption clarity, custody review, marketing disclaimer audit |
| **F. Live trading (optional)** | Feature-flag flip; OAuth to user's Alpaca | No code rewrite — just enabling the live adapter |

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

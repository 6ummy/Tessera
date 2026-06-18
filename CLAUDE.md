# CLAUDE.md — operator handbook for AI sessions (zero-context handoff)

You are working on **Tessera** with 정우 (@6ummy, Korean, replies in
Korean — answer in Korean, keep code/identifiers/commits in English).
Read this file top to bottom once; it is written so you can act without
any prior conversation.

## 1. What this product is

4 AI analyst personas — Warren (value), Cathie (disruptive growth +
crypto), Ray (macro regime allocator, ETF book), Peter (GARP) — write
weekly Sonnet 4.6 investment theses over a shared market-data plane.
A deterministic paper engine executes each persona's book against a
$100K virtual account; the Next.js site shows their books, P&L, and a
live chat with each persona. **Paper trading only. `FEATURE_LIVE_TRADING`
stays false until Phase E/F legal clearance — never flip it.**

Monorepo: `apps/web` (Next.js 14 App Router, Vercel) · `apps/worker`
(Python 3.11 FastAPI on Cloud Run `tessera-worker`, us-east1, project
`tessera-498200`) · `packages/shared` (Pydantic schemas) ·
`migrations/` (plain SQL → Neon Postgres + Timescale + pgvector,
**001–014 applied to prod (012 = additive `users` ALTER; 013 =
`follow_events`; 014 = `fcm_tokens`). users/user_portfolios already
exist from 001 §5**).

## 2. State as of 2026-06-16 — 🏁 **Phase C CLOSED · Phase D feature-complete (F&F onboarding left)**

Phase C acceptance 4/4 green (see Plan.md §5). 90-day baseline ran
2026-06-14: Warren Sharpe 1.28 (matches expected ~1.3), Cathie 3.21,
Peter 2.81, Ray 1.96 — all positive, all ordered by mandate (aggressive
growth > GARP > regime > value). The three Phase C carry-overs were
all closed before Phase D opens:

  - **`cost_namespace` isolation** (#132) — baseline runs write
    `cost_namespace='backtest_baseline'` into `llm_call_log`;
    `check_daily_budget()` filters those out so a one-off evaluation
    never starves the live system again.
  - **Quarterly margin YoY** (#133) — new `gross_margin_qtr_yoy_chg`
    column on `ticker_features`, populated Friday-only via the
    `fmp_quarterly` ingest step (last 8 quarters). Surfaces in the
    persona `<features>` block as `gross_margin_qtr_yoy=+200bps`.
  - **Normalized FCF yield** (#134) — new `fcf_yield_normalized`
    column = median of last 5 FY annual FCFs / mcap. Renders alongside
    trailing TTM in the prompt when both are non-NULL. Resolved the
    UNH-style "trailing 5.30% vs normalized 3%" mismatch as a metric-
    definition question, not a bug.
  - **Cathie shortlist hotfix** (#136) — `_tickers_for("cathie", n)`
    returns the full 14-name shortlist regardless of n so the crypto
    sleeve is always in the construction call's candidate set. The
    2026-06-14 baseline's 6-of-9-cells Tech-cap failures were the
    proximate trigger.

**Phase D (§6) FEATURE-COMPLETE**: Firebase Auth + Google SSO, `users`
table, single-follow CTA, `user_portfolios` + mirror engine, real
dashboard + account curve, FCM + email rebalance notify, chat memory
recall — all shipped (bullets below). **Only F&F onboarding (ops) and
turning the notification channels on (operator: VAPID/IAM/RESEND, runbook
§5/§6) remain.** Runs alongside Phase E (lawyer consult).

  - **Auth scaffolding shipped** (2026-06-16): `firebase` client SDK +
    `lib/firebase/client.ts` (lazy, env-gated) + `auth-context.tsx`
    (`AuthProvider`/`useAuth`) wired into the root layout; header now
    shows Sign-in / real user / Sign-out, falling back to the "jshin"
    pilot chip when `NEXT_PUBLIC_FIREBASE_*` is unset (so prod is never
    broken pre-config). Migration `012_users.sql` created. Operator
    setup: `docs/runbooks/firebase-auth.md`.
  - **Auth-sync shipped** (2026-06-16): `/api/auth/sync` (Edge) verifies
    the Firebase ID token with `jose` against Google's public JWKS (NO
    firebase-admin / service-account secret — only the public project id)
    and upserts the `users` row (`@neondatabase/serverless`, web→Neon
    direct for the USER layer; worker still owns the market-data plane).
    Client posts the token on sign-in + session restore. Needs
    `DATABASE_URL` set on Vercel.
  - **Follow shipped** (2026-06-16): `FollowButton` (sign-in-aware) on the
    persona detail sheet + dashboard + `/api/follow` (Edge: GET status /
    POST / DELETE). A follow seeds the user's $100K paper `user_portfolios`
    row (exists from 001; the row IS the follow — no separate `follows`
    table); unfollow drops it. **SINGLE-FOLLOW (product decision
    2026-06-16): one analyst at a time — POST drops any other follow first
    (logged as unfollow→follow in `follow_events`, so the account curve
    shows the switch).** User derived from the verified token only.
  - **Mirror engine shipped** (2026-06-16): nightly `mirror` step
    (`risk/mirror.py`, after `paper`, same flag) projects each persona's
    paper book onto its followers' `user_portfolios` by WEIGHT —
    `follower_nav = starting_capital × (persona_nav_today / persona_nav_at_follow_start)`,
    holdings carry the persona's current weights scaled to that NAV. No
    per-follower fill sim (deterministic, cheap, reconciles to the
    persona track); `started_at` anchors the baseline (no look-ahead).
  - **Dashboard wired to real follows** (2026-06-16): `GET
    /api/me/portfolios` (Edge, token-verified) reads `user_portfolios`;
    `/dashboard` portfolio tab renders real follows (multi-follow persona
    selector, positions table, tiles) with sign-in / no-follows empty
    states. Hardcoded `peter` mock gone. Social feed stays a labelled demo.
  - **Account curve** (2026-06-16): `follow_events` (migration 013) logs
    every follow/unfollow (best-effort write from `/api/follow`, never
    fails the follow); `GET /api/me/timeline` returns them; the dashboard
    chart reconstructs the account over the full ~1y S&P window via
    `lib/account-curve.ts` — flat (grey) in cash, tracking each persona's
    book while followed, **recoloured at every follow/unfollow**, S&P 500
    always drawn. Replaces the per-persona since-follow curve.
  - **FCM push shipped** (2026-06-16): web "Enable notifications" toggle →
    `getToken(VAPID)` → `/api/me/fcm-token` (`fcm_tokens`, migration 014) +
    `public/firebase-messaging-sw.js`; worker `notify/fcm.py` pushes
    followers on rebalance from `persona_batch` (best-effort, never breaks
    the batch). **Keyless send**: worker SA OAuth from the Cloud Run
    metadata server → FCM v1; needs the SA granted
    `roles/firebasecloudmessaging.admin` on `tessera-641a5` + flags
    `FEATURE_FCM_PUSH=true` (worker) + `NEXT_PUBLIC_FIREBASE_VAPID_KEY` /
    `_MESSAGING_SENDER_ID` (Vercel). Ships dark until then. Runbook §5.
  - **Email notify shipped** (2026-06-16): `notify/email.py` emails a
    persona's followers (via `users.email`) on rebalance, in PARALLEL with
    FCM — `persona_batch._notify_followers` fires both, each isolated.
    Resend HTTP API; gated on `FEATURE_EMAIL_NOTIFY` + `RESEND_API_KEY`
    (+ `EMAIL_FROM`). Ships dark. Runbook §6. (Email is the iOS / opt-out
    fallback web push can't reach.) **Per-user opt-out**: dashboard
    "Email alerts" switch → `/api/me/preferences` writes
    `users.preferences.email_notify`; the worker query skips users with
    it set `false` (default ON).
  - **Chat memory recall shipped** (2026-06-16, #168): `agents/chat.py`
    `_build_memory_block` recalls the persona's OWN past theses from
    `persona_memory` (pgvector cosine to the user message, cross-ticker;
    recency fallback), injected as a "things you've written before —
    reference, don't fabricate" block. Logs `chat.memory_recall
    strategy=similarity|recency`. (Was the last deferred Phase-D item.)
  - **NOT yet wired**: onboard 3 F&F users (ops); FCM/email channels need
    the operator to set VAPID/IAM/RESEND + redeploy (runbook §5/§6).

Prior state snapshot (pre-closure):

Everything below is LIVE in prod unless marked otherwise:

- **Daily 16-step ingest**, weekdays 21:30 UTC: Vercel cron →
  `/api/cron/daily` → Cloud Run `/jobs/ingest-daily` → ohlcv (Alpaca +
  Coinbase) → FRED → fundamentals 3-tier (FMP → SEC XBRL → FMP
  key-metrics → yfinance shares daily / history Fri) → news → SEC
  filings → features → coverage audit → **SPY canary** (>100bps vs
  Yahoo fails the run; baseline 2.62bps) → **paper engine** → **mirror
  engine** (followers) (both `FEATURE_PAPER_EXECUTION=true`).
  Advisory-locked (dup trigger no-ops).
- **Weekly persona batch**, Fri 22:00 UTC: v2 two-pass — research call
  per shortlist ticker, then ONE construction call per persona →
  `normalize_book` (deterministic sum=1.0) → **risk gateway** →
  ONE `analyst_reports` row per persona. Hallucination canary chains after.
- **Paper track**: engine bootstrapped 4 × $100K on 2026-06-11 (36
  fills); plus a **251-day hypothetical backfill** per persona
  (frozen-book: current holdings projected back 1y, `hypothetical=true`
  flag in DB/API, look-ahead bias). 1y hypothetical: ray +16.0%,
  peter +8.4%, cathie −2.0%, warren −7.0%. **UI policy (product decision
  2026-06-12): one solid line per persona, no dashed split — captions
  state "real fills since Jun 11, 2026"; the hypothetical flag stays in
  the data and `/api/performance` for any future use.**
- **Frontend**: all real — reports/proposals/chat (since 06-05),
  performance/portfolio (since 06-12, mock deleted). Dashboard "My
  portfolio" is now real (follows via `/api/me/portfolios`, 06-16).
  Remaining mock: the Social tab only (Phase-D demo, labelled). Auth is
  LIVE in prod (Firebase project `tessera-641a5`, Google SSO, 06-16);
  the "jshin" pilot chip is the fallback only when `NEXT_PUBLIC_FIREBASE_*`
  is unset (local/unconfigured).
- **Observability**: Grafana Cloud dashboard over `llm_call_log`
  (`docs/grafana/llm-cost-dashboard.json`); cross-source disagreement
  audit panel over `cross_source_disagreements` (#125,
  `docs/grafana/cross-source-disagreements-dashboard.json`);
  `coverage_gap` + `mcap_gap_yf_also_failed` daily warning streams from
  the post-build audit step; Sentry errors-only; Voyage embeddings on
  prod (similarity recall fires in the WEEKLY BATCH logs as `sim=0.xx`,
  and in CHAT as `chat.memory_recall strategy=similarity` since 2026-06-16
  — chat now recalls the persona's past theses cross-ticker via
  `_build_memory_block`). Slack alert webhook at
  $5/$10/$20 spend thresholds is LIVE (2026-06-16, operator-wired Grafana
  contact point + alert rules over `llm_call_log`; no code). The
  `check_daily_budget()` hard-pause remains the safety net; the alert is
  the earlier warning.
- **CI** (`.github/workflows/ci.yml`): ruff + pytest + mypy ALL
  blocking (mypy via a legacy `ignore_errors` ledger in
  `apps/worker/pyproject.toml` — NEW modules must be strict-clean and
  must NOT be added to the ledger). gitleaks pre-commit configured.
- **Risk/analytics layer (#105–#108, deployed 06-12 PM)**: gateway now
  full — VaR99 (`risk/var.py`, per-persona caps calibrated vs measured
  books) + drawdown floor (live track only) + Ray's `gate_regime`;
  weight-distribution telemetry (canary check 6, §11 tripwire);
  ticker-level attribution (`/api/attribution`, contributions sum to
  period return); paper-engine failures page via explicit Sentry
  capture + operator alert rule. Known: warren/cathie's pre-#94 books
  violate SECTOR caps → the next Friday batch re-shapes them via retry
  feedback (expected `risk_gateway.rejected` → `passed` log pairs).
- **PR trail this week**: #90 audit hotfixes → #93 re-land Steps 1+2 →
  #94 risk gateway → #95/#96 paper engine + flag → #98 Ray as_of fix →
  #99 mypy/tests/observability → #100 backfill → #103 frontend swap →
  #105 VaR/DD/Ray gate → #106 weight telemetry → #107 attribution →
  #108 Sentry paging → #110 parse-leading-prose → #111 recall sim= fix
  → #112 case-studies → #114 cathie sector cap 0.70 → #116 Cloud Run
  Jobs → #117 attribution UI → #118 main.py mypy burn → #120 coverage
  yf-also-failed → #121 fy_end_month FCF anchor → #122 paper-engine
  integrity gates → #123 mypy ledger -3 modules → #124 hit_rate FIFO →
  #125 cross-source disagreement Grafana → #128 FCF staleness guard
  (COIN) → #129 CS-13 + freshness invariant → #130 UNH not-a-bug
  reframe → #131 Phase C closure → #132 cost_namespace isolation →
  #133 quarterly gross_margin YoY → #134 fcf_yield_normalized → #135
  Plan checkbox cleanup → #136 Cathie shortlist hotfix → #137 Phase D
  docs sync → #139 deploy `-ImageTag` normalize (bare/full) + Jobs
  cmd echo → #143 advisory-lock `conn.commit()` root-cause (CS-14) →
  #144 fcf_yield_normalized loader form/fp + cap 8→24 (CS-15, norm
  1→38).

## 3. Hard invariants (each from a real incident — don't relearn them)

- **`ohlcv_1d` = ONE row per (ticker, calendar day).** Mixed sources
  once stored the same day twice (Alpaca 04:00Z vs Yahoo 00:00Z) and
  silently halved every row-window feature horizon for ~6y (P0-1, #90).
  New read paths: `DISTINCT ON (ticker, ts::date)` with source priority
  alpaca/coinbase > yahoo. Backfills must skip covered days. The
  nightly SPY canary is the tripwire.
- **Numbers in Python, narrative in LLM.** `features/compute.py` is the
  only path numbers reach prompts. The LLM never computes a price,
  weight, or P&L. Sizing intent from the LLM is normalized
  deterministically (`normalize_book`).
- **Book readers scope to `MAX(as_of_date)` only.** v2 writes one row
  per persona per batch; unioning across batch days resurrects dropped
  tickers ("ghost positions", P0-2).
- **Server-authoritative fields are force-set, never `setdefault`.**
  Ray's LLM volunteered its own `as_of` and won the tie for weeks (#98).
- **Every book passes `risk/gateway.py` pre-persist** — stock-pickers
  via `gate()`, Ray via `gate_regime()`: universe membership, sum=1.0,
  single-name + sector caps, parametric VaR99 vs calibrated persona
  caps (3.5/8.5/4.5/2.5%), drawdown floor on the LIVE track
  (20/35/25/15%). Rejection reasons feed the construction retry.
  "VaR unmeasurable" (<60 aligned obs) is soft — never rejects.
  Active position COUNT is also hard-gated in construction (each
  persona's [min,max]; Cathie's max is 12 since 2026-06-15).
  **Why hard-gate even when the prompt already states the caps**:
  CS-11 documents Cathie repeatedly busting the sector cap after
  explicit error feedback — LLM role-immersion can outweigh stated
  rules, so the system-level stop is non-negotiable for the limits that
  matter. **Cathie is the deliberate exception on SECTOR specifically:
  her sector cap was removed (2026-06-15) — tech/S-curve concentration
  is her mandate, not a risk to fence. `max_sector >= 1.0` means "no
  cap" and the gateway skips the sector check for her; her risk stays
  bounded by single-name 16% + VaR99 8.5% + the 35% drawdown floor.**
  The CS-11 lesson holds: drop a cap because it's the wrong tool, never
  because the LLM keeps busting it.
- **Paper engine**: NAV conservation exact (no fees v1), execution
  idempotent via `report_id` on `persona_trades`, fills at next bar
  OPEN, MTM at CLOSE. Hypothetical rows are write-guarded
  (`WHERE hypothetical`) — real rows are untouchable by the backfill.
- **Budgets**: every Anthropic call logs to `llm_call_log`. Global
  $5/day + chat-only $2/day pool (public chat must not starve Friday's
  batch). `check_daily_budget()` hard-pauses.
- **Chat is public until Phase D** — keep the guards: message ≤4K,
  history sanitized ≤20 turns, Edge 10/min/IP rate limit.
- **yfinance**: core dependency, but strictly tier-3 fallback,
  sanity-enveloped; its steps fail loudly if missing.
- **Sanity bound ≠ freshness check.** ±100% / margin envelopes / P/E
  caps catch unit + currency errors, NOT "upstream provider's mapping
  silently dropped → loader walked back to a 2.7-yr stale row that
  happens to be in-band" (CS-13, COIN). Every value that comes out of
  a loader walk-back must carry its newest-period_end meta forward;
  downstream guards drop values whose freshness exceeds a clear bound
  (FCF: `FCF_STALENESS_MAX_DAYS=400` ≈ 13 months).
- **Long-running jobs must not hold an idle-in-transaction connection,
  and teardown must never flip a successful run to failed** (CS-14).
  `try_advisory_lock` commits right after acquiring (SQLAlchemy 2.0
  future-mode opens an implicit txn on first `execute()`; Neon's
  `idle_in_transaction_session_timeout` ~5 min reaps it mid-run, which
  also made the end-of-run `pg_advisory_unlock` throw → Job exit 1 on
  an otherwise-green 15-step run). SESSION-level advisory locks survive
  a commit, so the lock still protects the whole run; the unlock is
  also `suppress`-wrapped as belt-and-suspenders. General rule:
  cleanup/finally exceptions are isolated from the result, and a Job's
  exit code must reflect the WORK, not a benign teardown error.
- **A compute fn only works if the loader supplies the shape it
  assumes** (CS-15). `_annual_income_rows` decides annual-ness by
  `period IN ('FY','Q4') OR form='10-K' OR fp='FY'`; EDGAR cash-flow
  rows have `period=NULL` and mark annual via `form`/`fp`. When
  `fcf_yield_normalized` reused that helper on `cash_rows` but the
  loader didn't SELECT `form`/`fp`, the fn silently returned None for
  ~39 EDGAR tickers (norm 1/59, no error). When wiring a reused helper
  onto a new source, confirm the source carries every field the helper
  reads. Debug order for "code is right but the column is empty":
  image-tag-time vs merge-time + Job exit code FIRST (confirms code
  ran), then look at the function's INPUT shape — not the deploy.
- **No silent failures — this codebase's #1 bug class** (see CS-3,
  CS-4, CS-5, CS-6, CS-12, CS-13, CS-15 in `docs/case-studies.md` for
  the canonical cases). Every caught exception logs loudly with context
  or re-raises;
  `suppress` / `except: pass` / `setdefault` on LLM-overlapping fields
  need written justification. A step where every item "skipped" is a
  FAILURE, not a success. **Don't pass the full universe to a
  source-specific ingest** — equity steps send `by_asset_class("equity")
  +("etf")` only; Alpaca rejects a crypto symbol and fails the whole
  batch (CS-12, hidden for 9 days because the Service ignored exit
  codes). When you fix a nontrivial bug, ADD A CS ENTRY to
  case-studies.md (presentation material) in the same PR.
- **Tailwind only emits classes whose literal string it SCANS** (CS-17).
  `apps/web/tailwind.config.ts` `content` must include EVERY dir holding
  class-name literals — `lib/` included (it has `ACCENT_CLASS` with the
  persona accent classes like `bg-plum-500`). A dynamic class registry in
  an unscanned dir only "works" by accidental duplication elsewhere; a
  refactor that removes the duplicate silently drops the class for the
  rarest value (Ray/plum). Prefer inline `style={{background: hex}}` for
  per-value colors.

## 4. Commands (Windows / PowerShell)

```powershell
# Worker — venv EXISTS at apps/worker/.venv, never recreate it
cd apps\worker
.\.venv\Scripts\python.exe -m pytest tests -q                          # 283 tests, no DB needed
.\.venv\Scripts\python.exe -m ruff check tessera_worker tests scripts  # MUST stay 0
.\.venv\Scripts\python.exe -m mypy tessera_worker                      # MUST stay 0
.\.venv\Scripts\python.exe -m tessera_worker.jobs.ingest_daily --only features coverage

# Web
cd apps\web
npm run typecheck    # tsc --noEmit
npm run lint

# Deploy worker (rebuild + ship; operator runs it, or hand them the cmd).
# After Service deploys, the script prints the exact tag + a copy-paste
# command for deploying the SAME image to Jobs (Service + Jobs MUST run
# the same code or the new column writes / chat path diverge).
.\apps\worker\scripts\deploy_cloud_run.ps1
.\apps\worker\scripts\deploy_cloud_run_jobs.ps1 -ImageTag "<tag printed above>"
# -ImageTag accepts either a bare tag ("20260615-002125") or a full
# reference. Omit it and the Jobs script builds a fresh image (5-7min).
# Flag-only change without rebuild:
#   gcloud run services update tessera-worker --region us-east1 --update-env-vars K=V
```

**DB access**: psql is NOT installed locally. Read-only queries → write
a small script using `tessera_worker.db.session_scope` and run it with
the venv python (this is routine and allowed). Schema changes / row
deletes → migrations applied by the operator in the Neon console SQL
editor. Never run prod-mutating jobs without explicit user consent in
the conversation.

## 5. Architecture in one breath

Vercel cron → Cloud Run FastAPI (`tessera_worker/main.py`) →
`jobs/ingest_daily.py` STEPS dict (idempotent, advisory-locked) →
Neon. Weekly: `jobs/persona_batch.py run_batch_v2` →
`agents/portfolio_construction.py` (+ `risk/gateway.py`) →
`analyst_reports`. Nightly: `risk/paper_engine.py` (fill/MTM/perf) →
`persona_trades` / `persona_portfolios` / `persona_performance`.
UI reads via worker HTTP endpoints proxied by Next Edge routes
(`apps/web/app/api/*` → IAM identity token via `lib/gcp-auth.ts`).

Key worker endpoints: `/api/reports/{p}`, `/api/proposals/{p}` (latest
batch day only), `/api/performance/{p}` (curve + hypothetical flags),
`/api/portfolio/{p}` (real snapshot only), `/api/attribution/{p}`
(?period=mtd|7d|30d), `/api/features/{t}`, `/api/prices/{t}`,
`/api/chat/{p}` (SSE), `/jobs/ingest-daily`, `/jobs/persona-batch`.

Key tables: `ohlcv_1d`, `ticker_features` (the only numbers LLMs see;
`fcf_yield` / `fcf_yield_normalized` / `gross_margin_qtr_yoy_chg` /
`market_cap_usd` / `peg` / etc.), `fundamentals` (JSONB, 3-tier merged
across FMP / EDGAR XBRL / yfinance / fmp_key_metrics), `analyst_reports`
(parsed book JSONB; `rejected` flag), `persona_trades/portfolios/
performance` (+ `hypothetical` flag), `llm_call_log` (+ `cost_namespace`
for baseline isolation), `persona_memory` (pgvector),
`cross_source_disagreements` (mcap candidate spread audit).

## 6. Process rules (violations have burned us)

- main is branch-protected: every change = branch → squash-merge PR.
  Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Stacked PRs: merge bottom-up AND delete each base branch** — GitHub
  only retargets children when the base is deleted; #91/#92 once merged
  into their bases instead of main and needed a cherry-pick re-land (#93).
  When unsure: `gh pr view N --json baseRefName,state`.
- PowerShell here-strings break `git commit -m` / `gh pr create --body`
  → always write to a temp file, use `-F` / `--body-file`.
- Repo text has UTF-8 em-dashes/box-chars; PowerShell `Get-Content`
  reads them as cp1252 mojibake. **Use the Read tool for Edit match
  strings; never bulk-rewrite files via PowerShell `-replace`** (it
  corrupted paper_engine.py once; had to restore from git).
- **`curl` in PowerShell is an alias for `Invoke-WebRequest`, NOT real
  curl.** `-H "Authorization: Bearer X"` fails with `Cannot bind
  parameter 'Headers'. Cannot convert ... String to ... IDictionary`.
  Either: (a) call real curl as `curl.exe -H "..."`, or (b) use the
  native form `Invoke-WebRequest -Uri ... -Headers @{ "Authorization"
  = "Bearer $TOKEN" }`. Same trap appears for any `-H` / `--header` /
  `-d` flag you copy-pasted from a Linux/Mac snippet.
- **Cloud Run worker is `--no-allow-unauthenticated`** — only
  `serviceAccount:tessera-vercel@...` is bound to `roles/run.invoker`.
  Direct `curl https://tessera-worker-...` from a dev box returns
  `Error: Forbidden / Your client does not have permission` at
  Google's edge (the request never reaches the app). For ad-hoc
  testing add your own user once with
  `gcloud run services add-iam-policy-binding tessera-worker --region
  us-east1 --member="user:<email>" --role="roles/run.invoker"`, then
  pass an ID token via `gcloud auth print-identity-token`. Health
  checks are rarely needed anyway — a `gcloud run services describe`
  showing the latest revision as `Ready` is a stronger signal than
  `/health` 200 (readiness probe already gated it).
- **Deploy = build, then EXECUTE.** `deploy_cloud_run.ps1` builds +
  ships the Service and prints the image tag + the exact
  `deploy_cloud_run_jobs.ps1 -ImageTag "<tag>"` line to reuse that
  build for the Jobs. `deploy_cloud_run_jobs.ps1 -ImageTag` accepts a
  bare tag (`20260615-002125`) OR a full ref — a bare tag used to be
  passed verbatim to `--image` and gcloud read it as a Docker Hub
  library image (`Image 'mirror.gcr.io/library/<tag>' not found`); #139
  normalizes both. **Deploying a Job only updates its image — features
  are NOT recomputed until you `gcloud run jobs execute
  tessera-ingest-daily --region us-east1 --wait`.** "I redeployed but
  the column is still empty" almost always means the job wasn't
  executed (or you're reading before it finished). Confirm with the
  execution list timestamp, not assumptions (CS-15).
- The operator (정우) runs gcloud/Neon/Vercel console steps — hand exact
  commands. Verify their reports with read-only queries when cheap.
- After any ohlcv-touching migration: rebuild features
  (`--only features coverage`) + run SPY canary.
- Docs are part of done: update Plan.md (+ its versioning table),
  architecture.md, improvement plan, and this file in the same PR as
  the change they describe.

## 7. Debugging entry points

- Cron ran? `gcloud logging read "resource.labels.service_name=tessera-worker" --freshness=1d`
  (filter `textPayload:paper_engine`, `:sim=`, `:step_failed` as needed).
- Data fresh? `SELECT MAX(fetched_at) FROM news;` / latest `ts` per table.
- Ticker blank in UI? `python -m scripts.inspect_ticker_features <T>`
  walks the whole fundamentals fall-through.
- Book looks wrong? Check `analyst_reports` latest `as_of_date` row's
  `parsed`, then `risk_gateway.*` log lines, then `paper_engine.*`.
- Cost spike? Grafana dashboard or `SELECT stage, SUM(cost_usd) FROM
  llm_call_log WHERE ts >= CURRENT_DATE GROUP BY 1;`

## 8. Backlog (priority order, with pointers)

1. **90-day point-in-time backtest baseline** — credibility anchor;
   harness exists (`jobs/backtest_harness.py`), ~$10–20 LLM. Plan §5 Week 5.
2. **mypy ledger burn-down** — 5 modules left. Burned: `features/compute.py`
   + `agents/anthropic_runner.py` + `agents/prompt_assembler.py`
   (2026-06-14); `agents.portfolio_construction` + `agents.ticker_resolver`
   + `agents.chat` (2026-06-16, #148); the 4 demo modules (2026-06-16, #169
   — stdout.reconfigure stub gap, read_sql params cast, PERSONA: PersonaId).
   Remaining: the ingestors.* glob + the 4 jobs (hallucination_canary,
   persona_batch, backtest_harness, backfill_history).
3. **hit_rate** (needs closed-lot tracking) · quarterly margin series
   ingest (low) · §10 weight-authority decision once a few weeks of
   `canary.weight_telemetry` accumulate. Phase D feature-complete (auth /
   follow / mirror / dashboard / notify / chat memory all shipped) —
   remaining is F&F onboarding + the operator notification enable.

Done 2026-06-12/13: Gateway VaR/DD/Ray + attribution endpoint + weight
telemetry (#105–#108); **Cloud Run Jobs migration** (#116,
`deploy_cloud_run_jobs.ps1` + `docs/runbooks/cloud-run-jobs.md` — batches
run to completion, no more BackgroundTask reaping; the cutover
[Cloud Scheduler on, Vercel crons off] is an operator console step; the
first test-run also surfaced CS-12, fixed in #119);
**attribution UI table** in the detail sheet (#117); **main.py mypy
burn-down** (#118); **equity-ingest crypto-exclusion** (#119, CS-12 —
equity OHLCV had silently frozen 9 days because Alpaca rejected a
crypto symbol and the Service ignored the exit code).

## 9. Doc map

`README.md` (quick start) → `architecture.md` (system + data flow +
file map; §6 is current-state) → `Plan.md` (phase roadmap; §5 = Phase C
live state; versioning table at bottom) →
`docs/improvement-plan-2026-06-11.md` (the audit that drove this week;
P0–P3 + step statuses) → per-phase "Lessons" live INSIDE Plan.md
(§3 Phase A, §4 Phase B, §5 Phase C running list — keep that
convention, no separate retro files) → **`docs/case-studies.md`**
(presentation-ready bug write-ups CS-1…CS-10; append on every
nontrivial fix) → `docs/runbooks/` (observability, Cloud Run IAM)
→ `personalities.md`
(persona specs — TEAM-OWNED, big voice changes need a 카톡 heads-up).
CONTRIBUTING.md has the team/track map (5 people; you mostly interact
with 정우).

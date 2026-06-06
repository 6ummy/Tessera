# Quant Demo — read → compute → screen

Concrete walkthrough for **예슬 / 준원** and anyone adding a new feature in
Phase B. Pairs with `demo_fcf_yield.py` in this directory. A sister
script `demo_data_explorer.py` shows ASCII sparklines of every series
already in Neon — run it once to grok how much data you have.

```bash
cd apps/worker
.\.venv\Scripts\Activate.ps1            # mac/linux: source .venv/bin/activate

# (a) See what's in the DB right now — universe coverage + price + macro sparklines
python -m tessera_worker.features.demo_data_explorer

# (b) Compute FCF yield + Warren screen
python -m tessera_worker.features.demo_fcf_yield

# (c) Discover which macros drive which tickers (auto-generates
#     TICKER_MACRO_OVERLAY dict for LLM Pipeline + suggests new features)
python -m tessera_worker.features.demo_macro_sensitivity
```

The FCF demo connects to the shared Neon DB (using `DATABASE_URL` from
your `apps/worker/.env`), pulls the latest close per ticker and the latest
annual fundamentals, computes **FCF yield = FCF / (close × shares)**, and
prints a ranked ASCII bar chart. The explorer demo is read-only — just
sparklines and tables so you can answer "what data do we have?" in 5 sec.
No matplotlib, no Jupyter, no setup — just `python -m`.

**Fundamentals coverage**: 39/42 equities (was 20/42 pre-2026-06-02 when
SEC XBRL companyfacts ingestor shipped). 3 still missing: BRK.B (ticker
dot/dash), ASML + TSM (foreign filers, submit 20-F not 10-K).

**Price/macro depth**: full backfill done 2026-06-02 — Alpaca 6 yrs,
Coinbase 11 yrs, FRED to each series' inception (UNRATE → 1948).

## What you should see

```
=== FCF yield screen (49 equities) ===

  META      ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇  6.42%
  GOOGL     ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇      5.21%
  CVX       ▇▇▇▇▇▇▇▇▇▇▇▇          3.92%
  AAPL      ▇▇▇▇▇▇▇▇▇▇            3.30%
  ...
  TSLA      ▇                     0.45%

Top 5: META, GOOGL, CVX, AAPL, MSFT  ← these are Warren's screen candidates
```

The bar width is proportional to FCF yield — easy to eyeball which names
are screaming cheap on cash flow. (Warren typically wants > 6%.)

## Extend this — common follow-ups

The whole point of the demo is to be a starting branch. Here are 4
"so what's next?" moves that take ~5 lines each:

### Sector overlay
Add a column for the GICS sector (from `universe.py` metadata) and group
the bars. Reveals if cheap FCF yield is just an energy/utility bias:

```python
from tessera_worker.universe import TICKERS
sector_by = {t.ticker: t.sector for t in TICKERS}
df["sector"] = df["ticker"].map(sector_by)
print(df.groupby("sector")["fcf_yield"].agg(["mean", "count"]))
```

### Historical trend, not just snapshot
The demo uses the most recent fundamentals row. Change it to pull 5 years
and watch FCF yield evolve — is it trending or stable?

```python
# Replace step 2's "DISTINCT ON (ticker)" with a window grab:
"... WHERE period_type = 'annual' AND ticker = 'AAPL' ORDER BY period DESC LIMIT 5"
```

### Wire into ticker_features (the actual production path)
> ✅ **Shipped 2026-06-04 → 2026-06-06.** `fcf_yield` shipped first across
> PRs #37 / #38 / #39; the Phase C quality-feature pass then added PEG,
> EPS CAGR, debt/equity, gross margin, and margin trend using the same
> pure-function + loader + latest-row upsert pattern.

What's now live in `compute.py`:

- `compute_fcf_yield()` — pure function: TTM FCF (USD) ÷ today's mcap
- `sum_ttm_fcf()` — TTM rollup robust to three FMP data shapes (annual
  FY rows, quarterly standalones, cumulative-YTD-per-FY). The
  cumulative case decomposes precisely via
  `TTM = last_FY + current_YTD − prior_FY_YTD_at_same_period`.
- `FX_TO_USD` — currency conversion for non-USD reporters (TWD, EUR,
  GBP, JPY, KRW, HKD, CNY, CAD). Unknown currency → drop.
- `cross_validated()` + `estimate_market_cap()` — agreement-based mcap
  from 4 candidates (close × diluted, close × basic, payload cash, payload
  income). Disagreement → conservative max.
- `±100%` sanity bound on yield (`FCF_YIELD_SANITY_BOUND`).
- `compute_eps_cagr_3y()` — diluted EPS CAGR from annual income rows,
  anchored roughly three fiscal years back; drops non-positive EPS.
- `compute_peg()` — trailing PEG proxy: `(close / latest EPS) ÷
  (EPS CAGR × 100)`. True forward PEG still awaits analyst-estimate data.
- `compute_debt_to_equity()` — total debt / stockholders' equity, with
  long-term + short-term debt fallback when total debt is missing.
- `compute_gross_margin()` + `compute_gross_margin_trend()` — current
  gross margin plus latest-minus-three-years-ago trend.
- `build(*, with_fundamentals: bool = True)` — flexibility toggle.
  Default daily; toggle exists for future cadence splits.

Live state after the 2026-06-06 local rebuild: the features step wrote
~259K price/momentum rows across 53 tickers and latest fundamentals-derived
features for 40 tickers. Representative `fcf_yield` values from the earlier
shipping pass:

| Ticker | Yield | Notes |
|---|---|---|
| XOM, MA, JNJ | 3–5% | top of the screen (Warren-friendly) |
| AAPL, MSFT, COST | 2–3% | mid (matches independently-computed real) |
| TSM | 1.5% | currency-converted from TWD |
| PLTR, TSLA | <1% | cash-burning growth — sub-bound, but in band |

**Still deferred to Phase C** (data-quality work): UNH, NVDA, AMZN, COIN
edge cases (sparse FY anchors, alternating null filings, one-time
spikes). Sanity bound prevents pollution of the LLM prompt; full fix
needs a dedicated daily mcap source (FMP `key_metrics`) and FY-aware
ingestion.

Recipe for the next feature in the backlog (use the same scaffold):

1. Pure function in `compute.py` (`compute_<feature>()`), with
   `cross_validated()` over whatever candidate sources exist.
2. Loader extension: pull additional fields into `_load_fundamentals_latest`.
3. Wire into `build()`'s fundamentals pass.
4. Tests in `test_features.py` (worked examples + edge cases).
5. PR titled `feat(features): add <feature> to ticker_features`.

### Property test the math
```python
from hypothesis import given, strategies as st

@given(
    fcf=st.floats(min_value=1, max_value=1e12, allow_nan=False),
    close=st.floats(min_value=0.01, max_value=10_000, allow_nan=False),
    shares=st.floats(min_value=1, max_value=1e11, allow_nan=False),
)
def test_fcf_yield_invariant(fcf, close, shares):
    y = fcf / (close * shares)
    assert y > 0
    assert y * close * shares == fcf       # algebra holds
```

## Why these inputs

The demo touches 3 tables — they're the minimum needed for any
fundamentals-driven feature:

| Table | Read what | Why |
|---|---|---|
| `ohlcv_1d` | latest `close` per ticker | market cap = price × shares |
| `fundamentals` | latest annual `cash_flow`, `balance_sheet` | FCF (numerator) + shares outstanding (denominator) |
| `universe.py` (in-code) | ticker list | gives us the scope, not the DB |

For features that also need momentum (Cathie) or correlation (risk
gateway), pull from `ticker_features` (already-computed) or `ohlcv_1d`
(raw history) instead of recomputing.

## Fundamentals features now live

The production `ticker_features` boundary now includes:

1. **`fcf_yield`** — TTM FCF / fresh USD market cap.
2. **`peg`** — trailing proxy until an analyst-estimates source lands.
3. **`eps_cagr_3y`** — durability of earnings growth.
4. **`debt_to_equity`** — risk hygiene; gate rather than primary signal.
5. **`gross_margin`** and **`gross_margin_trend`** — quality/scaling signal.
6. **`operating_margin`** and **`market_cap_usd`** — support fields for
   prompts, risk checks, and auditability.

Remaining backlog:

- **`news_sentiment_30d`** — needs an LLM/local model. **Defer to Phase C.**
- **Dedicated daily market-cap source** — add FMP `key_metrics` as a fifth
  market-cap candidate to tighten the known FCF-yield edge cases.

Each follows the same 5-step recipe (migration → compute.py → test → apply → PR).

## New macro signals (2026-06-02 expansion) — opportunities

`macro_series` grew from 20 → 37 series. The new ones unlock features
that weren't computable before:

| New series | Feature idea | Owner persona |
|---|---|---|
| DCOILWTICO, DCOILBRENTEU | `oil_beta_30d` — rolling regression of ticker return vs WTI return. Useful for energy names (XOM, CVX) and airlines/transports. | Warren, Ray |
| DHHNGSP | `gas_beta_30d` — same idea for utilities (NEE). | Warren |
| DEXCHUS, DEXJPUS, DEXKOUS | `fx_beta_<pair>_30d` — ticker return vs currency move. Detects ADR / international-exposure stocks (TSM, BABA, ASML). | Cathie, Ray |
| BAMLH0A0HYM2 | `hy_spread_change_30d` — credit cycle proxy. When HY spread widens > 50 bps in 30d → cycle stress. Use as risk-gate input in Phase C. | Ray, Peter |
| BAMLH0A0HYM2 - DGS10 | `credit_risk_premium` — HY spread minus 10Y as a single "risk-off" scalar. | Ray |

Pattern: same `features/compute.py` style as `fcf_yield` — small pandas
function reading `macro_series` + `ohlcv_1d`, writing back to
`ticker_features`. These are mostly **per-ticker × per-day** features so
they fit the existing schema without column-explosion.

Heads-up: copper and wheat are monthly cadence; resample to daily with
forward-fill before computing rolling betas, or skip them for daily
features and use only for slow-moving signals.

## Read more

- `architecture.md` §6 "How to read the data we've stored" — the longer
  SQL cheatsheet and Python connection patterns.
- `Plan.md` §4 "Week 2 Quickstart" — track-level guidance for Phase B.
- This file's sibling: `agents/LLM_pipeline_demo.md` — the LLM side of
  the same data flow.

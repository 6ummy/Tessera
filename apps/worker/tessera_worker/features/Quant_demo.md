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
The demo doesn't write back (the `WRITE_BACK` flag is off). To make this
a real feature consumed by the LLM personas:

1. Open `migrations/` — write `002_add_fcf_yield.sql` adding the column.
2. Open `compute.py` `build()` — fold the compute step in. Pattern:
   ```python
   df = pd.merge(features_df, fcf_yield_df, on="ticker", how="left")
   ```
3. Open `tests/test_features.py` — add a hypothesis test (random
   positive FCF + positive shares + positive close → fcf_yield is finite
   and matches FCF / (close × shares)).
4. Apply migration to Neon: `psql "$DATABASE_URL" -f migrations/002_*.sql`.
5. PR with title `feature(quant): add fcf_yield to ticker_features`.

After PR merge + next daily cron run, every persona's prompt assembler
will see `ticker_features.fcf_yield` automatically. Warren's screen will
start using it as a hard input.

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

## Phase B feature backlog — pick one to ship

In priority order (Warren + Peter > Cathie > Ray):

1. **`fcf_yield`** — what this demo computes. **Ship first.**
2. **`peg_ratio`** = forward P/E ÷ 3y EPS CAGR. Peter primary screen.
3. **`eps_cagr_3y`** — durability of growth. Warren + Peter both want.
4. **`debt_to_equity`** — risk hygiene; every persona uses it as a
   gate, not a primary signal.
5. **`gross_margin_trend`** — Cathie's "is it scaling?" detector.
6. **`news_sentiment_30d`** — needs an LLM/local model. **Defer to Phase C.**

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

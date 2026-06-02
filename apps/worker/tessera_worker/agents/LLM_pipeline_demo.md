# LLM Pipeline Demo — assemble a persona's daily thesis input

Concrete walkthrough for **윤채 / 한솔** and anyone building the persona
runner in Phase B. Pairs with `demo_warren_aapl.py` in this directory.

```bash
cd apps/worker
.\.venv\Scripts\Activate.ps1            # mac/linux: source .venv/bin/activate

# (a) See what data Warren can actually pull from (universe + history depth)
python -m tessera_worker.features.demo_data_explorer

# (b) Assemble a real prompt for Warren on AAPL
python -m tessera_worker.agents.demo_warren_aapl
```

> **Data depth note (2026-06-02)**: fundamentals now cover 39/42 equity
> tickers (was 20/42) thanks to the SEC XBRL companyfacts ingestor.
> Equity price history backfilled to ~20 yrs per US-listed name via
> yfinance one-off pull (Alpaca's 6 yrs lives alongside under
> `source='alpaca'`). Macro back to series inception (some go to 1948).
>
> The demo now uses two new prompt blocks that exercise this depth:
>   `<price_history>` — 20-yr ASCII sparkline + total return + worst
>     drawdown in window. Warren sees Apple survived '08 −56% and '20
>     COVID; Cathie sees TSLA's 2x post-2019 trajectory.
>   `<financials_trend>` — 5 most-recent annual filings as a table
>     (revenue / op income / net income / FCF / LT debt) + auto-computed
>     revenue CAGR. AAPL's "+3.3%/yr CAGR" line is the literal data
>     point that triggers Warren's slowdown thesis.
>
> When you fork this for other personas: keep the data-gathering identical,
> change only the render order + which blocks to include. Ray would drop
> `<price_history>` and `<filing>` and add 30 more macro series; Cathie
> would expand `<news>` and shrink `<financials_trend>` to 3 years.

The script connects to the shared Neon DB, gathers all six inputs Warren's
prompt would need to write a real thesis on AAPL, then **renders a fully
assembled mock system prompt** to stdout. That's exactly what
`prompt_assembler.py` will produce programmatically for every
(persona × shortlisted ticker) pair, daily.

## What you should see

```
=== Warren | AAPL | 2026-06-01 ===

<features>
  ret_1d=+0.42%  ret_30d=+5.10%  ret_1y=+18.3%
  vol_30d=22%  RSI14=58  SMA20=$235.40
</features>

<financials period="2025-09-30">
  Revenue:   $391.0 B
  Op income: $123.2 B
  Free CF:   $108.8 B   <- Warren's anchor
  Total debt:$104.2 B
</financials>

<context>
  10Y yield: 4.32%   10Y breakeven: 2.41%   HY spread: 312 bps
</context>

<news count=5>
  [n_91024] 2026-05-30 [Bloomberg] Apple's Services revenue accelerates...
  [n_91012] 2026-05-29 [Reuters]   App Store ruling appeal granted, ...
  ...
</news>

<filing form="10-K" filed="2025-10-30">
  (first 800 chars of MD&A)
  ...Apple Inc. designs, manufactures and markets smartphones, personal computers,
  tablets, wearables and accessories... Net sales increased 2% year-over-year,
  driven by Services growth...
</filing>

--- assembled prompt (3,142 tokens) ---
[full prompt printed here so you can copy-paste into the Anthropic console]
```

The output is **runnable input for Claude**. Paste the assembled prompt
into the Anthropic console and you'll get Warren's first thesis — same
data the real persona runner will see.

## Extend this — common follow-ups

The whole point of the demo is to be a starting branch. Here are four
moves that take ~10 lines each:

### Swap personas without touching the data layer
The demo's data-gathering is persona-agnostic. The persona-specific cuts
are at the *end* (rendering). Swap `persona="warren"` for `cathie` to see
that Cathie wants more news, less 10-K:

```python
RENDER_RULES = {
    "warren":  {"news_limit": 5,  "include_filing": True,  "news_min_ret_30d": 0},
    "cathie":  {"news_limit": 12, "include_filing": False, "news_min_ret_30d": 0},
    "ray":     {"news_limit": 0,  "include_filing": False, "include_macros": "all"},
    "peter":   {"news_limit": 8,  "include_filing": True,  "news_min_ret_30d": 0.10},
}
```

This is the per-persona cut table from `Plan.md` §4 made executable.

### Pick the right macro series per (persona, ticker)
The `macro_series` table has 37 FRED series (yields, FX, energy, credit
spreads, etc.). Each persona/ticker pair should pull only the ~3–8 that
actually move that thesis — feeding all 37 every call wastes tokens.

**The demo file already implements this pattern** — `MACRO_BY_PERSONA` and
`TICKER_MACRO_OVERLAY` dicts at the top of `demo_warren_aapl.py`, composed
by the `macros_for(persona, ticker)` helper. The query in `fetch_inputs()`
calls that helper instead of using a hardcoded list. Ray's persona is
declared as `"ALL"` and the query special-cases that to pull every series.

**The overlay is data-driven, not guessed**: run
`python -m tessera_worker.features.demo_macro_sensitivity` to compute
60-day rolling correlations between each ticker's daily return and every
macro series's daily delta, ranked by absolute correlation. The script
prints a copy-pasteable `TICKER_MACRO_OVERLAY = {...}` dict you can drop
into `demo_warren_aapl.py`. Re-run weekly to keep aligned with regime.

Real values from the 2026-06-02 audit (top-3 macro per ticker):

```python
MACRO_BY_PERSONA = {
    "warren": ["DGS10", "T10YIE", "BAMLH0A0HYM2", "VIXCLS"],     # base
    "cathie": ["DGS10", "VIXCLS", "BAMLC0A0CM"],                  # rate-sensitive growth + IG spread
    "ray":    "ALL",                                              # regime model wants everything
    "peter":  ["DGS10", "T10YIE", "BAMLH0A0HYM2", "UNRATE"],     # rate + employment cycle
}

# Per-ticker overlays — add these on top of the persona base:
TICKER_MACRO_OVERLAY = {
    "AAPL":  ["DEXCHUS"],                       # Greater China lever (~20% revenue)
    "MSFT":  ["DEXUSEU"],                       # EMEA exposure
    "GOOGL": ["DEXUSEU", "DEXJPUS"],            # broad international
    "XOM":   ["DCOILWTICO", "DCOILBRENTEU"],    # oil price = revenue
    "CVX":   ["DCOILWTICO", "DCOILBRENTEU"],
    "NEE":   ["DHHNGSP"],                       # nat gas fuel cost
    "ASML":  ["DEXUSEU", "DEXKOUS"],            # Dutch HQ + Korean fab customers
    "TSM":   ["DEXJPUS", "DEXCHUS"],            # Taiwan/Asian export channel
    "BKNG":  ["DEXUSEU", "DEXJPUS"],            # travel FX exposure
    "WMT":   ["DEXMXUS"],                       # Mexico ops
    # ... fill the rest as theses are written
}

def macro_for(persona: str, ticker: str) -> list[str]:
    base = MACRO_BY_PERSONA[persona]
    if base == "ALL":
        return ALL_37_SERIES_IDS
    return base + TICKER_MACRO_OVERLAY.get(ticker, [])
```

The demo's `WARREN_MACRO_SERIES` constant already shows this pattern with
DEXCHUS + WTI added to Warren's AAPL-specific cut. Extend to the other
(persona, ticker) combos as the universe screen produces shortlists.

### Loop the universe
The demo runs one (persona, ticker). Real persona runner does:

```python
shortlist = screen(persona="warren")  # top 30 by fcf_yield, debt/equity, etc.
for ticker in shortlist:
    prompt = build_prompt("warren", ticker)
    report = call_claude(prompt)
    insert_into_analyst_reports(report)
```

The `screen()` step is where the **Haiku universe screen** lives (cheap, fast).
Only the top 30 names per persona graduate to a Sonnet thesis call.

### Real Anthropic call
The demo only prints the prompt. To actually call Claude:

```python
import anthropic
client = anthropic.Anthropic()
resp = client.messages.create(
    model="claude-sonnet-4-5",   # confirm model id; current default per ADR-003
    max_tokens=4096,
    system=[
        {"type": "text", "text": persona_spec, "cache_control": {"type": "ephemeral"}},
    ],
    messages=[
        {"role": "user", "content": assembled_prompt},
    ],
)
parsed = AnalystReport.model_validate_json(resp.content[0].text)
```

`cache_control: ephemeral` on the persona spec keeps ~2-3K tokens cached
across calls — saves real money once you loop the universe.

### Citation validation
Every news item rendered has an `id` like `[n_91024]`. Warren is *required*
to cite by that id when he references a news event. Validator pattern:

```python
def validate_citations(report: AnalystReport, news_ids: set[str]) -> list[str]:
    """Return list of cited ids that don't resolve to a real news row."""
    return [c for c in report.cited_news_ids if c not in news_ids]
```

If non-empty -> reject the thesis, retry once with feedback. Phase B
acceptance criteria say <2% schema failure rate; this is one of the most
common ways the rate creeps up.

## Why these inputs

The six blocks map directly to the six tables Phase A populated:

| Block | Source table | Why |
|---|---|---|
| `<features>` | `ticker_features` | Numbers Warren can quote as evidence |
| `<financials>` | `fundamentals` | Computes FCF yield, P/E from JSON |
| `<context>` | `macro_series` | Regime in which Warren is operating |
| `<news>` | `news` | Events relevant in the last 7 days |
| `<filing>` | `filings` + GCS | Direct quotes from management |
| (price history) | `ohlcv_1d` | Sparkline rendering in UI; LLM sees stats |

For chat (Phase B Week 3), you'd add a 7th block: `<history>` with the
conversation transcript. Same pattern, different source (`chat_messages`
table that Week 3 will add).

## Where this fits in the agents/ module (the real one you build)

```
agents/
  __init__.py
  persona_loader.py        # parse personalities.md sections, cache in memory
  prompt_assembler.py      # the production version of demo_warren_aapl.py
  anthropic_runner.py      # typed Anthropic call, retry on schema fail
  citation_validator.py    # the validate_citations() above, productionized
  models.py                # AnalystReport, Proposal Pydantic schemas
  demo_warren_aapl.py      # this demo (stays as a smoke test)
  LLM_pipeline_demo.md     # this doc
```

## Output goes to `analyst_reports`

After the real runner validates the LLM response, it writes:

```python
session.execute(text("""
    INSERT INTO analyst_reports
        (persona_id, ts, inputs_hash, parsed, raw_response, cost_usd)
    VALUES (:p, NOW(), :h, :parsed, :raw, :cost)
"""), {
    "p": "warren",
    "h": inputs_hash,           # SHA256 of (feature_snapshot + filing_id + news_ids)
    "parsed": parsed.model_dump_json(),
    "raw": resp.content[0].text,
    "cost": cost_usd,           # from resp.usage × pricing per model
})
```

The frontend swap (Week 3) reads from `analyst_reports`. So as soon as you
ship the first persona runner, the UI can light up.

## Read more

- `architecture.md` §6 "How to read the data we've stored" — longer SQL reference.
- `Plan.md` §4 "Week 2 Quickstart" — track-level guidance.
- `personalities.md` — Warren's voice rules, hard rules, output schema.
- `docs/adr/004-four-personas-and-voice-gatekeeper.md` — why 4 personas, why this voice model.
- This file's sibling: `features/Quant_demo.md` — the Quant side of the same data plane.

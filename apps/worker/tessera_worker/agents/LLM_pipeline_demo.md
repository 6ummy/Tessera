# LLM Pipeline Demo — assemble a persona's daily thesis input

Concrete walkthrough for **윤채 / 한솔** and anyone building the persona
runner in Phase B. Pairs with `demo_warren_aapl.py` in this directory.

```bash
cd apps/worker
.\.venv\Scripts\Activate.ps1            # mac/linux: source .venv/bin/activate
python -m tessera_worker.agents.demo_warren_aapl
```

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

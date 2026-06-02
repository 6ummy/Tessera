"""Warren | AAPL prompt-assembly demo.

Pulls all six inputs Warren's daily thesis prompt would need from Neon,
renders them as named blocks the real prompt_assembler will produce, and
prints the final assembled prompt as runnable Claude input.

Run:  python -m tessera_worker.agents.demo_warren_aapl
See:  agents/LLM_pipeline_demo.md  for context + extension recipes.

No Anthropic API call here — just the assembly. Once persona_loader +
anthropic_runner exist, swap the print() at the bottom for a real call.

Schema notes (fundamentals): three rows per period_end per ticker, one
each for filing_type in ('income','balance','cash_flow'); the financial
fields live in payload JSONB.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from textwrap import shorten

from sqlalchemy import text

from tessera_worker.db import session_scope

# Force UTF-8 stdout so Japanese/Chinese chars in news titles don't crash
# on Windows cp1252. Safe on Mac/Linux too.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass  # python < 3.7 or non-text stream


TICKER = "AAPL"
PERSONA = "warren"
NEWS_LOOKBACK_DAYS = 7

# Warren cares about real rates + breakevens + HY credit spread + VIX
# for "what regime am I operating in" framing. Other personas would pick
# different series; see LLM_pipeline_demo.md "Swap personas" section.
WARREN_MACRO_SERIES = (
    "DGS10",         # 10Y real rate proxy
    "T10YIE",        # 10Y breakeven inflation
    "BAMLH0A0HYM2",  # HY OAS — credit cycle
    "VIXCLS",        # vol regime
    "DEXCHUS",       # USD/CNY — AAPL Greater China revenue exposure (~20%)
    "DCOILWTICO",    # WTI — input cost signal (small for AAPL, big for XOM)
)


def fetch_inputs() -> dict:
    """Pull the six blocks Warren needs for AAPL."""
    out: dict = {}
    with session_scope() as session:
        # 1. Feature snapshot
        feat = session.execute(text("""
            SELECT ts, ret_1d, ret_5d, ret_30d, ret_90d, ret_1y,
                   vol_30d, rsi_14, sma_20, sma_50, volume_z
            FROM ticker_features WHERE ticker = :t
            ORDER BY ts DESC LIMIT 1
        """), {"t": TICKER}).mappings().first()
        out["features"] = dict(feat) if feat else None

        # 2. Price history — leverage the 20-yr yfinance + 6-yr Alpaca depth
        # we backfilled in Phase C pre-ship. Warren is a long-term investor,
        # so we want a full historical sparkline (drawdown context) AND the
        # last 30 closes (chart in UI). DISTINCT ON dedupes the Alpaca/Yahoo
        # same-day rows (different time-of-day -> different PK; pick the
        # deepest-history source per calendar day).
        all_prices = session.execute(text("""
            SELECT DISTINCT ON (ts::date) ts::date AS d, close, source
            FROM ohlcv_1d
            WHERE ticker = :t
            ORDER BY ts::date,
                     CASE source WHEN 'yahoo' THEN 1
                                 WHEN 'alpaca' THEN 2
                                 WHEN 'coinbase' THEN 3
                                 ELSE 9 END
        """), {"t": TICKER}).all()
        out["prices_full"] = [(p.d, float(p.close)) for p in all_prices]
        # Last 30 trading days for the inline chart in the prompt
        out["prices_recent"] = out["prices_full"][-30:]

        # 3. Fundamentals — three filing types × LATEST 5 annual + LATEST 5 quarterly
        # gives Warren the 5yr revenue / margin / FCF trend he actually values.
        # Distinguishing annual vs quarterly via the `form` field in payload
        # (10-K = annual, 10-Q = quarterly — set by SEC XBRL ingestor; FMP
        # rows have no `form` field so they're treated as "unknown" and
        # included as backup).
        funds = {}
        for ft in ("income", "balance", "cash_flow"):
            # Last 5 annual filings (10-K) — Warren's primary lens
            annual_rows = session.execute(text("""
                SELECT period_end, payload FROM fundamentals
                WHERE ticker = :t AND filing_type = :ft
                  AND (payload ->> 'form' = '10-K' OR payload ->> 'fp' = 'FY')
                ORDER BY period_end DESC LIMIT 5
            """), {"t": TICKER, "ft": ft}).mappings().all()
            funds[ft] = [dict(r) for r in annual_rows]
        out["fundamentals_annual"] = funds
        # Also keep latest-of-each for the existing single-period block
        funds_latest = {}
        for ft in ("income", "balance", "cash_flow"):
            row = session.execute(text("""
                SELECT period_end, payload FROM fundamentals
                WHERE ticker = :t AND filing_type = :ft
                ORDER BY period_end DESC LIMIT 1
            """), {"t": TICKER, "ft": ft}).mappings().first()
            funds_latest[ft] = dict(row) if row else None
        out["fundamentals"] = funds_latest

        # 4. Macro context — latest value per series (each FRED series has
        #    its own update cadence: yields/FX/oil daily, CPI/M2 monthly).
        #    DISTINCT ON guarantees one row per series_id even when dates differ.
        macros = session.execute(text("""
            SELECT DISTINCT ON (series_id) series_id, value, ts
            FROM macro_series
            WHERE series_id = ANY(:ids)
            ORDER BY series_id, ts DESC
        """), {"ids": list(WARREN_MACRO_SERIES)}).all()
        out["macros"] = {r.series_id: float(r.value) for r in macros}

        # 5. News
        news = session.execute(text("""
            SELECT id, ts, source, title FROM news
            WHERE :t = ANY(tickers) AND ts >= :since
            ORDER BY ts DESC LIMIT 10
        """), {"t": TICKER, "since": date.today() - timedelta(days=NEWS_LOOKBACK_DAYS)}).all()
        out["news"] = [
            {"id": str(n.id), "ts": n.ts, "source": n.source, "title": n.title}
            for n in news
        ]

        # 6. Filing — latest 10-K
        filing = session.execute(text("""
            SELECT filing_type, filing_date, period_end, text_summary, raw_gcs_uri
            FROM filings
            WHERE ticker = :t AND filing_type = '10-K'
            ORDER BY filing_date DESC LIMIT 1
        """), {"t": TICKER}).mappings().first()
        out["filing"] = dict(filing) if filing else None

    return out


# ─────────────────────────────────────────────────────────────────────────
# Rendering — turn raw data into named blocks
# ─────────────────────────────────────────────────────────────────────────
def _fmt_money(v) -> str:
    """Format a number as $X.YB or 'n/a'."""
    if v is None or v == "":
        return "n/a"
    try:
        n = float(v)
        return f"${n / 1e9:.1f}B"
    except (TypeError, ValueError):
        return "n/a"


def render_features(f: dict | None) -> str:
    if not f:
        return "<features>(no data)</features>"
    return (
        "<features>\n"
        f"  asof={f['ts']}\n"
        f"  returns:  1d={f['ret_1d']:+.2%}  5d={f['ret_5d']:+.2%}  "
        f"30d={f['ret_30d']:+.2%}  90d={f['ret_90d']:+.2%}  1y={f['ret_1y']:+.2%}\n"
        f"  vol_30d={f['vol_30d']:.2%}  RSI14={f['rsi_14']:.0f}  "
        f"SMA20=${f['sma_20']:.2f}  SMA50=${f['sma_50']:.2f}\n"
        f"  volume_z={f['volume_z']:+.2f}\n"
        "</features>"
    )


SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float], width: int = 40) -> str:
    if not values:
        return "(empty)"
    if len(values) > width:
        bucket = len(values) / width
        out = []
        for i in range(width):
            chunk = values[int(i * bucket):int((i + 1) * bucket)]
            if chunk:
                out.append(sum(chunk) / len(chunk))
        values = out
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return SPARKLINE_CHARS[0] * len(values)
    step = (vmax - vmin) / (len(SPARKLINE_CHARS) - 1)
    return "".join(SPARKLINE_CHARS[min(int((v - vmin) / step), 7)] for v in values)


def render_price_history(prices_full: list[tuple]) -> str:
    """Long-term sparkline + summary stats. Uses the 20-yr yfinance depth."""
    if not prices_full:
        return "<price_history>(no data)</price_history>"
    closes = [p[1] for p in prices_full]
    first_dt, last_dt = prices_full[0][0], prices_full[-1][0]
    spark = _sparkline(closes, width=50)
    years = (last_dt - first_dt).days / 365.25
    total_ret = (closes[-1] / closes[0] - 1) * 100
    peak = max(closes)
    # Drawdown from all-time-high to now (negative = we're below peak)
    pct_off_ath = (closes[-1] / peak - 1) * 100 if peak > 0 else 0
    # Worst peak-to-trough drawdown across the entire window
    worst_dd = 0.0
    running_peak = closes[0]
    for c in closes:
        if c > running_peak:
            running_peak = c
        dd = (c / running_peak - 1) * 100
        if dd < worst_dd:
            worst_dd = dd
    return (
        f"<price_history span=\"{first_dt} to {last_dt}\" years=\"{years:.1f}\">\n"
        f"  {spark}\n"
        f"  start=${closes[0]:.2f}  end=${closes[-1]:.2f}  total_return={total_ret:+.0f}%\n"
        f"  all-time-high=${peak:.2f}  current_vs_ATH={pct_off_ath:+.0f}%\n"
        f"  worst_drawdown_in_window={worst_dd:+.0f}%\n"
        "</price_history>"
    )


def render_fundamentals(funds: dict) -> str:
    """funds = {'income': {...} | None, 'balance': {...}, 'cash_flow': {...}}"""
    if not funds or not any(funds.values()):
        return "<financials>(no data)</financials>"

    inc = (funds.get("income") or {}).get("payload") or {}
    bs  = (funds.get("balance") or {}).get("payload") or {}
    cf  = (funds.get("cash_flow") or {}).get("payload") or {}

    period = (funds.get("income") or funds.get("cash_flow") or {}).get("period_end")
    return (
        f"<financials period=\"{period}\">\n"
        f"  Revenue:    {_fmt_money(inc.get('revenue'))}\n"
        f"  Op income:  {_fmt_money(inc.get('operatingIncome'))}\n"
        f"  Net income: {_fmt_money(inc.get('netIncome'))}\n"
        f"  Free CF:    {_fmt_money(cf.get('freeCashFlow'))}      <- Warren's anchor\n"
        f"  Op cash flow:{_fmt_money(cf.get('operatingCashFlow'))}\n"
        f"  Long-term debt: {_fmt_money(bs.get('longTermDebt'))}\n"
        f"  Cash + ST inv: {_fmt_money(bs.get('cashAndShortTermInvestments'))}\n"
        f"  Shares (weighted): {inc.get('weightedAverageShsOut', 'n/a')}\n"
        "</financials>"
    )


def render_fundamentals_trend(funds_annual: dict) -> str:
    """5-year annual trend table — Warren's actual lens for durability."""
    if not funds_annual:
        return "<financials_trend>(no annual data)</financials_trend>"

    inc_rows = funds_annual.get("income", [])
    cf_rows = funds_annual.get("cash_flow", [])
    bs_rows = funds_annual.get("balance", [])
    if not inc_rows and not cf_rows:
        return "<financials_trend>(no annual data)</financials_trend>"

    # Build a per-period view, most-recent-first
    by_period: dict = {}
    for row in inc_rows:
        p = row["period_end"]
        by_period.setdefault(p, {})["inc"] = row["payload"]
    for row in cf_rows:
        p = row["period_end"]
        by_period.setdefault(p, {})["cf"] = row["payload"]
    for row in bs_rows:
        p = row["period_end"]
        by_period.setdefault(p, {})["bs"] = row["payload"]
    periods = sorted(by_period.keys(), reverse=True)[:5]

    def fmt(payload_block: dict | None, key: str) -> str:
        if not payload_block:
            return "n/a"
        v = payload_block.get(key)
        if v is None:
            return "n/a"
        try:
            return f"${float(v) / 1e9:.1f}B"
        except (TypeError, ValueError):
            return "n/a"

    lines = ["<financials_trend rows=\"5 most recent annual filings\">"]
    lines.append(f"  {'period':<12}  {'revenue':>10}  {'op_inc':>10}  "
                 f"{'net_inc':>10}  {'FCF':>10}  {'lt_debt':>10}")
    for p in periods:
        b = by_period[p]
        lines.append(
            f"  {str(p):<12}  "
            f"{fmt(b.get('inc'), 'revenue'):>10}  "
            f"{fmt(b.get('inc'), 'operatingIncome'):>10}  "
            f"{fmt(b.get('inc'), 'netIncome'):>10}  "
            f"{fmt(b.get('cf'), 'freeCashFlow'):>10}  "
            f"{fmt(b.get('bs'), 'longTermDebt'):>10}"
        )
    # 5-year CAGR if both endpoints have revenue
    try:
        first_rev = float(by_period[periods[-1]]["inc"]["revenue"])
        last_rev = float(by_period[periods[0]]["inc"]["revenue"])
        years = (periods[0] - periods[-1]).days / 365.25
        if years > 0 and first_rev > 0:
            cagr = (last_rev / first_rev) ** (1 / years) - 1
            lines.append(f"  -> revenue CAGR over {years:.1f}yr: {cagr*100:+.1f}%/yr")
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    lines.append("</financials_trend>")
    return "\n".join(lines)


def render_macros(m: dict) -> str:
    if not m:
        return "<context>(no macro data)</context>"
    parts = []
    if "DGS10" in m:        parts.append(f"10Y yield: {m['DGS10']:.2f}%")
    if "T10YIE" in m:       parts.append(f"10Y breakeven: {m['T10YIE']:.2f}%")
    if "BAMLH0A0HYM2" in m: parts.append(f"HY spread: {m['BAMLH0A0HYM2']:.2f}%")
    if "VIXCLS" in m:       parts.append(f"VIX: {m['VIXCLS']:.1f}")
    if "DEXCHUS" in m:      parts.append(f"USD/CNY: {m['DEXCHUS']:.2f} (AAPL Greater China lever)")
    if "DCOILWTICO" in m:   parts.append(f"WTI: ${m['DCOILWTICO']:.1f}/bbl")
    return "<context>\n  " + "\n  ".join(parts) + "\n</context>"


def render_news(items: list[dict]) -> str:
    if not items:
        return "<news count=0>(none in window)</news>"
    lines = [f"<news count={len(items)}>"]
    for n in items:
        title = shorten(n["title"], width=90, placeholder="...")
        lines.append(f"  [n_{n['id'][:8]}] {n['ts'].date()} [{n['source']}] {title}")
    lines.append("</news>")
    return "\n".join(lines)


def render_filing(f: dict | None) -> str:
    if not f:
        return "<filing>(no 10-K available — run sec_edgar ingest for this ticker)</filing>"
    excerpt = shorten(f["text_summary"] or "", width=800, placeholder="...")
    return (
        f"<filing form=\"{f['filing_type']}\" filed=\"{f['filing_date']}\" "
        f"period_end=\"{f['period_end']}\" gcs=\"{f['raw_gcs_uri']}\">\n"
        f"  (first 800 chars; full text in GCS)\n"
        f"  {excerpt}\n"
        "</filing>"
    )


def render_prompt(persona: str, ticker: str, blocks: dict) -> str:
    """Stitch the named blocks into one assembled prompt body.

    Note the order: short-term snapshot (features) -> long-term context
    (price history + multi-year financials) -> macro -> news -> filing.
    Warren weights the long-term blocks heavily; Cathie would invert.
    """
    return "\n\n".join([
        f"You are {persona}, the persona defined in personalities.md.",
        f"Today's analysis target: {ticker}",
        render_features(blocks["features"]),
        render_price_history(blocks["prices_full"]),
        render_fundamentals(blocks["fundamentals"]),
        render_fundamentals_trend(blocks["fundamentals_annual"]),
        render_macros(blocks["macros"]),
        render_news(blocks["news"]),
        render_filing(blocks["filing"]),
        "Write today's thesis on the target ticker. Output JSON matching the "
        "AnalystReport schema. Cite news by id (e.g. [n_91024])."
    ])


def main() -> int:
    print(f"\n=== {PERSONA} | {TICKER} | {date.today()} ===\n")
    blocks = fetch_inputs()

    # Each block first — scan-friendly
    print(render_features(blocks["features"]));            print()
    print(render_price_history(blocks["prices_full"]));    print()
    print(render_fundamentals(blocks["fundamentals"]));    print()
    print(render_fundamentals_trend(blocks["fundamentals_annual"])); print()
    print(render_macros(blocks["macros"]));                print()
    print(render_news(blocks["news"]));                    print()
    print(render_filing(blocks["filing"]));                print()

    # Assembled prompt — what you'd paste into the Anthropic console
    assembled = render_prompt(PERSONA, TICKER, blocks)
    est_tokens = len(assembled) // 4
    print("-" * 72)
    print(f"--- assembled prompt (~{est_tokens:,} tokens) ---")
    print("-" * 72)
    print(assembled)
    print()
    print("Next: paste the assembled prompt into the Anthropic console to see")
    print("Warren's first thesis. Wire to anthropic_runner.py for automation.")
    print("See agents/LLM_pipeline_demo.md for the production wiring pattern.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

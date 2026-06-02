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
WARREN_MACRO_SERIES = ("DGS10", "T10YIE", "BAMLH0A0HYM2", "VIXCLS")


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

        # 2. Price history (LLM gets summary stats; UI gets the points)
        prices = session.execute(text("""
            SELECT ts, close FROM ohlcv_1d
            WHERE ticker = :t ORDER BY ts DESC LIMIT 30
        """), {"t": TICKER}).all()
        out["prices"] = [(p.ts, float(p.close)) for p in prices]

        # 3. Fundamentals — three separate rows per period, joined here
        funds = {}
        for ft in ("income", "balance", "cash_flow"):
            row = session.execute(text("""
                SELECT period_end, payload
                FROM fundamentals
                WHERE ticker = :t AND filing_type = :ft
                ORDER BY period_end DESC LIMIT 1
            """), {"t": TICKER, "ft": ft}).mappings().first()
            funds[ft] = dict(row) if row else None
        out["fundamentals"] = funds

        # 4. Macro context
        macros = session.execute(text("""
            SELECT series_id, value FROM macro_series
            WHERE series_id = ANY(:ids)
              AND ts = (SELECT MAX(ts) FROM macro_series WHERE series_id = 'DGS10')
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


def render_macros(m: dict) -> str:
    if not m:
        return "<context>(no macro data)</context>"
    parts = []
    if "DGS10" in m:        parts.append(f"10Y yield: {m['DGS10']:.2f}%")
    if "T10YIE" in m:       parts.append(f"10Y breakeven: {m['T10YIE']:.2f}%")
    if "BAMLH0A0HYM2" in m: parts.append(f"HY spread: {m['BAMLH0A0HYM2']:.0f} bps")
    if "VIXCLS" in m:       parts.append(f"VIX: {m['VIXCLS']:.1f}")
    return "<context>\n  " + "   ".join(parts) + "\n</context>"


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
    """Stitch the named blocks into one assembled prompt body."""
    return "\n\n".join([
        f"You are {persona}, the persona defined in personalities.md.",
        f"Today's analysis target: {ticker}",
        render_features(blocks["features"]),
        render_fundamentals(blocks["fundamentals"]),
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
    print(render_features(blocks["features"]));     print()
    print(render_fundamentals(blocks["fundamentals"])); print()
    print(render_macros(blocks["macros"]));          print()
    print(render_news(blocks["news"]));              print()
    print(render_filing(blocks["filing"]));          print()

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

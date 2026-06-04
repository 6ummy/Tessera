"""Assemble persona thesis prompts from Neon data + personalities.md spec.

Production version of demo_warren_aapl.py: fetch inputs, render XML-ish blocks,
merge with optional memory recall, return system (persona spec) + user message.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from textwrap import shorten
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.agents.persona_loader import PersonaId, get_persona_spec
from tessera_worker.db import session_scope

# Per-persona macro base + ticker overlay (see demo_macro_sensitivity.py).
MACRO_BY_PERSONA: dict[str, list[str] | str] = {
    "warren": ["DGS10", "T10YIE", "BAMLH0A0HYM2", "VIXCLS"],
    "cathie": ["DGS10", "VIXCLS", "BAMLC0A0CM"],
    "ray": "ALL",
    "peter": ["DGS10", "T10YIE", "BAMLH0A0HYM2", "UNRATE"],
}

TICKER_MACRO_OVERLAY: dict[str, list[str]] = {
    "AAPL": ["VIXCLS", "BAMLH0A0HYM2", "DEXCHUS"],
    "AMZN": ["VIXCLS", "BAMLH0A0HYM2", "BAMLC0A0CM"],
    "ASML": ["VIXCLS", "DEXMXUS", "BAMLH0A0HYM2"],
    "GOOGL": ["VIXCLS", "BAMLH0A0HYM2", "DEXKOUS"],
    "META": ["BAMLH0A0HYM2", "VIXCLS", "BAMLC0A0CM"],
    "MSFT": ["BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS"],
    "NVDA": ["VIXCLS", "BAMLH0A0HYM2", "BAMLC0A0CM"],
    "TSLA": ["VIXCLS", "BAMLH0A0HYM2", "BAMLC0A0CM"],
    "TSM": ["VIXCLS", "BAMLH0A0HYM2", "DEXJPUS"],
    "XOM": ["DCOILWTICO", "DCOILBRENTEU", "DJFUELUSGULF"],
    "JPM": ["VIXCLS", "BAMLH0A0HYM2", "T10Y2Y"],
    "NEE": ["DHHNGSP", "DGS10", "UNRATE"],
    "HD": ["DCOILWTICO", "DGS10", "DJFUELUSGULF"],
    "JNJ": ["DGS10", "T10YIE", "DGS30"],
    "PG": ["T10YIE", "DGS10", "DGS2"],
    "WMT": ["DEXMXUS", "DGS10", "VIXCLS"],
}

RENDER_RULES: dict[PersonaId, dict[str, Any]] = {
    "warren": {
        "news_limit": 10,
        "news_lookback_days": 7,
        "include_filing": True,
        "include_price_history": True,
        "include_financials_trend": True,
    },
    "cathie": {
        "news_limit": 12,
        "news_lookback_days": 7,
        "include_filing": False,
        "include_price_history": True,
        "include_financials_trend": True,
    },
    "ray": {
        "news_limit": 0,
        "news_lookback_days": 7,
        "include_filing": False,
        "include_price_history": False,
        "include_financials_trend": False,
    },
    "peter": {
        "news_limit": 8,
        "news_lookback_days": 7,
        "include_filing": True,
        "include_price_history": True,
        "include_financials_trend": True,
    },
}

SERIES_FORMATTERS: dict[str, tuple[str, str]] = {
    "DGS2": ("2Y yield", "{:.2f}%"),
    "DGS10": ("10Y yield", "{:.2f}%"),
    "DGS30": ("30Y yield", "{:.2f}%"),
    "T10Y2Y": ("2s10s spread", "{:.2f}%"),
    "T10YIE": ("10Y breakeven", "{:.2f}%"),
    "T5YIFR": ("5y5y fwd infl", "{:.2f}%"),
    "CPIAUCSL": ("CPI level", "{:.1f}"),
    "PCEPILFE": ("Core PCE level", "{:.2f}"),
    "UNRATE": ("Unemployment", "{:.2f}%"),
    "PAYEMS": ("Nonfarm payrolls", "{:.0f}K"),
    "ICSA": ("Init claims", "{:.0f}K"),
    "INDPRO": ("Industrial prod", "{:.1f}"),
    "M2SL": ("M2", "${:.0f}B"),
    "WALCL": ("Fed BS", "${:.0f}M"),
    "DTWEXBGS": ("USD broad", "{:.2f}"),
    "VIXCLS": ("VIX", "{:.1f}"),
    "BAMLH0A0HYM2": ("HY OAS", "{:.2f}%"),
    "BAMLC0A0CM": ("IG OAS", "{:.2f}%"),
    "DEXUSEU": ("USD/EUR", "{:.4f}"),
    "DEXJPUS": ("JPY/USD", "{:.2f}"),
    "DEXKOUS": ("KRW/USD", "{:.2f}"),
    "DEXCAUS": ("CAD/USD", "{:.4f}"),
    "DEXSZUS": ("CHF/USD", "{:.4f}"),
    "DEXCHUS": ("USD/CNY", "{:.2f}"),
    "DEXUSUK": ("USD/GBP", "{:.4f}"),
    "DEXMXUS": ("MXN/USD", "{:.2f}"),
    "DEXINUS": ("INR/USD", "{:.2f}"),
    "DCOILWTICO": ("WTI", "${:.1f}/bbl"),
    "DCOILBRENTEU": ("Brent", "${:.1f}/bbl"),
    "DHHNGSP": ("NatGas (HH)", "${:.2f}/MMBtu"),
    "DJFUELUSGULF": ("Jet fuel", "${:.3f}/gal"),
    "PCOPPUSDM": ("Copper", "${:.0f}/MT"),
    "PWHEAMTUSDM": ("Wheat", "${:.0f}/MT"),
}

SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"


@dataclass(frozen=True)
class AssembledPrompt:
    persona_id: PersonaId
    ticker: str
    as_of: date
    system_prompt: str
    user_message: str
    news_ids: frozenset[str]
    inputs_hash: str


def macros_for(persona: PersonaId, ticker: str) -> list[str]:
    base = MACRO_BY_PERSONA.get(persona, [])
    if base == "ALL":
        return ["__ALL__"]
    overlay = TICKER_MACRO_OVERLAY.get(ticker, [])
    seen: set[str] = set()
    out: list[str] = []
    for s in list(base) + list(overlay):
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fetch_inputs(
    session: Session,
    persona: PersonaId,
    ticker: str,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Pull DB blocks for one (persona, ticker) pair."""
    rules = RENDER_RULES[persona]
    since = (as_of or date.today()) - timedelta(days=rules["news_lookback_days"])
    out: dict[str, Any] = {}

    feat = session.execute(
        text("""
            SELECT ts, ret_1d, ret_5d, ret_30d, ret_90d, ret_1y,
                   vol_30d, rsi_14, sma_20, sma_50, volume_z
            FROM ticker_features WHERE ticker = :t
            ORDER BY ts DESC LIMIT 1
        """),
        {"t": ticker},
    ).mappings().first()
    out["features"] = dict(feat) if feat else None

    all_prices = session.execute(
        text("""
            SELECT DISTINCT ON (ts::date) ts::date AS d, close, source
            FROM ohlcv_1d
            WHERE ticker = :t
            ORDER BY ts::date,
                     CASE source WHEN 'yahoo' THEN 1
                                 WHEN 'alpaca' THEN 2
                                 WHEN 'coinbase' THEN 3
                                 ELSE 9 END
        """),
        {"t": ticker},
    ).all()
    out["prices_full"] = [(p.d, float(p.close)) for p in all_prices]

    funds: dict[str, list[dict]] = {}
    for ft in ("income", "balance", "cash_flow"):
        annual_rows = session.execute(
            text("""
                SELECT period_end, payload FROM fundamentals
                WHERE ticker = :t AND filing_type = :ft
                  AND (payload ->> 'form' = '10-K' OR payload ->> 'fp' = 'FY')
                ORDER BY period_end DESC LIMIT 5
            """),
            {"t": ticker, "ft": ft},
        ).mappings().all()
        funds[ft] = [dict(r) for r in annual_rows]
    out["fundamentals_annual"] = funds

    funds_latest: dict[str, dict | None] = {}
    for ft in ("income", "balance", "cash_flow"):
        row = session.execute(
            text("""
                SELECT period_end, payload FROM fundamentals
                WHERE ticker = :t AND filing_type = :ft
                ORDER BY period_end DESC LIMIT 1
            """),
            {"t": ticker, "ft": ft},
        ).mappings().first()
        funds_latest[ft] = dict(row) if row else None
    out["fundamentals"] = funds_latest

    wanted = macros_for(persona, ticker)
    if wanted == ["__ALL__"]:
        macros = session.execute(
            text("""
                SELECT DISTINCT ON (series_id) series_id, value, ts
                FROM macro_series ORDER BY series_id, ts DESC
            """),
        ).all()
    else:
        macros = session.execute(
            text("""
                SELECT DISTINCT ON (series_id) series_id, value, ts
                FROM macro_series
                WHERE series_id = ANY(:ids)
                ORDER BY series_id, ts DESC
            """),
            {"ids": wanted},
        ).all()
    out["macros"] = {r.series_id: float(r.value) for r in macros}

    news_limit = rules["news_limit"]
    if news_limit > 0:
        news = session.execute(
            text("""
                SELECT id, ts, source, title FROM news
                WHERE :t = ANY(tickers) AND ts >= :since
                ORDER BY ts DESC LIMIT :lim
            """),
            {"t": ticker, "since": since, "lim": news_limit},
        ).all()
        out["news"] = [
            {"id": str(n.id), "ts": n.ts, "source": n.source, "title": n.title}
            for n in news
        ]
    else:
        out["news"] = []

    if rules["include_filing"]:
        filing = session.execute(
            text("""
                SELECT filing_type, filing_date, period_end, text_summary, raw_gcs_uri
                FROM filings
                WHERE ticker = :t AND filing_type = '10-K'
                ORDER BY filing_date DESC LIMIT 1
            """),
            {"t": ticker},
        ).mappings().first()
        out["filing"] = dict(filing) if filing else None
    else:
        out["filing"] = None

    out["memory"] = fetch_memory_recall(session, persona, ticker)
    return out


def fetch_memory_recall(
    session: Session,
    persona: PersonaId,
    ticker: str,
    limit: int = 3,
) -> str:
    rows = session.execute(
        text("""
            SELECT thesis_md, ts FROM persona_memory
            WHERE persona_id = :p AND ticker = :t
            ORDER BY ts DESC LIMIT :n
        """),
        {"p": persona, "t": ticker, "n": limit},
    ).all()
    if not rows:
        return ""
    lines = [f'<memory count="{len(rows)}">']
    for r in rows:
        snippet = shorten(r.thesis_md or "", width=400, placeholder="...")
        lines.append(f"  [{r.ts.date()}] {snippet}")
    lines.append("</memory>")
    return "\n".join(lines)


def _fmt_money(v: Any) -> str:
    if v is None or v == "":
        return "n/a"
    try:
        return f"${float(v) / 1e9:.1f}B"
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


def _sparkline(values: list[float], width: int = 40) -> str:
    if not values:
        return "(empty)"
    if len(values) > width:
        bucket = len(values) / width
        sampled: list[float] = []
        for i in range(width):
            chunk = values[int(i * bucket) : int((i + 1) * bucket)]
            if chunk:
                sampled.append(sum(chunk) / len(chunk))
        values = sampled
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return SPARKLINE_CHARS[0] * len(values)
    step = (vmax - vmin) / (len(SPARKLINE_CHARS) - 1)
    return "".join(
        SPARKLINE_CHARS[min(int((v - vmin) / step), 7)] for v in values
    )


def render_price_history(prices_full: list[tuple]) -> str:
    if not prices_full:
        return "<price_history>(no data)</price_history>"
    closes = [p[1] for p in prices_full]
    first_dt, last_dt = prices_full[0][0], prices_full[-1][0]
    spark = _sparkline(closes, width=50)
    years = (last_dt - first_dt).days / 365.25
    total_ret = (closes[-1] / closes[0] - 1) * 100
    peak = max(closes)
    pct_off_ath = (closes[-1] / peak - 1) * 100 if peak > 0 else 0
    worst_dd = 0.0
    running_peak = closes[0]
    for c in closes:
        if c > running_peak:
            running_peak = c
        dd = (c / running_peak - 1) * 100
        if dd < worst_dd:
            worst_dd = dd
    return (
        f'<price_history span="{first_dt} to {last_dt}" years="{years:.1f}">\n'
        f"  {spark}\n"
        f"  start=${closes[0]:.2f}  end=${closes[-1]:.2f}  total_return={total_ret:+.0f}%\n"
        f"  all-time-high=${peak:.2f}  current_vs_ATH={pct_off_ath:+.0f}%\n"
        f"  worst_drawdown_in_window={worst_dd:+.0f}%\n"
        "</price_history>"
    )


def render_fundamentals(funds: dict) -> str:
    if not funds or not any(funds.values()):
        return "<financials>(no data)</financials>"
    inc = (funds.get("income") or {}).get("payload") or {}
    bs = (funds.get("balance") or {}).get("payload") or {}
    cf = (funds.get("cash_flow") or {}).get("payload") or {}
    period = (funds.get("income") or funds.get("cash_flow") or {}).get("period_end")
    return (
        f'<financials period="{period}">\n'
        f"  Revenue:    {_fmt_money(inc.get('revenue'))}\n"
        f"  Op income:  {_fmt_money(inc.get('operatingIncome'))}\n"
        f"  Net income: {_fmt_money(inc.get('netIncome'))}\n"
        f"  Free CF:    {_fmt_money(cf.get('freeCashFlow'))}\n"
        f"  Op cash flow:{_fmt_money(cf.get('operatingCashFlow'))}\n"
        f"  Long-term debt: {_fmt_money(bs.get('longTermDebt'))}\n"
        f"  Cash + ST inv: {_fmt_money(bs.get('cashAndShortTermInvestments'))}\n"
        f"  Shares (weighted): {inc.get('weightedAverageShsOut', 'n/a')}\n"
        "</financials>"
    )


def render_fundamentals_trend(funds_annual: dict) -> str:
    if not funds_annual:
        return "<financials_trend>(no annual data)</financials_trend>"
    inc_rows = funds_annual.get("income", [])
    cf_rows = funds_annual.get("cash_flow", [])
    bs_rows = funds_annual.get("balance", [])
    if not inc_rows and not cf_rows:
        return "<financials_trend>(no annual data)</financials_trend>"

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

    lines = ['<financials_trend rows="5 most recent annual filings">']
    lines.append(
        f"  {'period':<12}  {'revenue':>10}  {'op_inc':>10}  "
        f"{'net_inc':>10}  {'FCF':>10}  {'lt_debt':>10}"
    )
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
    try:
        first_rev = float(by_period[periods[-1]]["inc"]["revenue"])
        last_rev = float(by_period[periods[0]]["inc"]["revenue"])
        years = (periods[0] - periods[-1]).days / 365.25
        if years > 0 and first_rev > 0:
            cagr = (last_rev / first_rev) ** (1 / years) - 1
            lines.append(f"  -> revenue CAGR over {years:.1f}yr: {cagr * 100:+.1f}%/yr")
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    lines.append("</financials_trend>")
    return "\n".join(lines)


def render_macros(m: dict) -> str:
    if not m:
        return "<context>(no macro data)</context>"
    lines = []
    for series_id, value in m.items():
        label, fmt = SERIES_FORMATTERS.get(series_id, (series_id, "{:.4f}"))
        try:
            v_str = fmt.format(float(value))
        except (TypeError, ValueError):
            v_str = str(value)
        lines.append(f"{label}: {v_str}")
    return f"<context count={len(lines)}>\n  " + "\n  ".join(lines) + "\n</context>"


def render_news(items: list[dict]) -> str:
    if not items:
        return "<news count=0>(none in window)</news>"
    lines = [f"<news count={len(items)}>"]
    for n in items:
        title = shorten(n["title"], width=90, placeholder="...")
        short_id = n["id"].replace("-", "")[:8]
        lines.append(f"  [n_{short_id}] {n['ts'].date()} [{n['source']}] {title}")
    lines.append("</news>")
    return "\n".join(lines)


def news_ids_from_items(items: list[dict]) -> frozenset[str]:
    return frozenset(n["id"] for n in items)


def render_filing(f: dict | None) -> str:
    if not f:
        return "<filing>(no 10-K available)</filing>"
    excerpt = shorten(f["text_summary"] or "", width=800, placeholder="...")
    return (
        f'<filing form="{f["filing_type"]}" filed="{f["filing_date"]}" '
        f'period_end="{f["period_end"]}" gcs="{f["raw_gcs_uri"]}">\n'
        f"  (first 800 chars; full text in GCS)\n"
        f"  {excerpt}\n"
        "</filing>"
    )


def build_user_message(
    persona: PersonaId,
    ticker: str,
    blocks: dict[str, Any],
) -> str:
    rules = RENDER_RULES[persona]
    parts = [
        f"Today's analysis target: {ticker}",
        render_features(blocks["features"]),
    ]
    if rules["include_price_history"]:
        parts.append(render_price_history(blocks["prices_full"]))
    parts.append(render_fundamentals(blocks["fundamentals"]))
    if rules["include_financials_trend"]:
        parts.append(render_fundamentals_trend(blocks["fundamentals_annual"]))
    parts.append(render_macros(blocks["macros"]))
    if blocks.get("memory"):
        parts.append(blocks["memory"])
    if rules["news_limit"] > 0:
        parts.append(render_news(blocks["news"]))
    if rules["include_filing"]:
        parts.append(render_filing(blocks["filing"]))
    parts.append(
        "Write today's thesis on the target ticker. Output JSON matching the "
        "AnalystReport schema (persona_id, as_of, proposals, cash_target, "
        "notes_to_manager). Cite news using the short identifier shown in the "
        "news block (e.g. \"n_b7a434db\") — the runner resolves these to full "
        "UUIDs automatically."
    )
    return "\n\n".join(parts)


def compute_inputs_hash(user_message: str) -> str:
    return hashlib.sha256(user_message.encode("utf-8")).hexdigest()


def assemble_prompt(
    persona: PersonaId,
    ticker: str,
    *,
    as_of: date | None = None,
    session: Session | None = None,
) -> AssembledPrompt:
    """Build system (persona spec) + user (data blocks) for one thesis call."""
    as_of = as_of or date.today()
    system_prompt = get_persona_spec(persona)

    def _build(sess: Session) -> AssembledPrompt:
        blocks = fetch_inputs(sess, persona, ticker, as_of=as_of)
        user_message = build_user_message(persona, ticker, blocks)
        news_ids = news_ids_from_items(blocks["news"])
        return AssembledPrompt(
            persona_id=persona,
            ticker=ticker,
            as_of=as_of,
            system_prompt=system_prompt,
            user_message=user_message,
            news_ids=news_ids,
            inputs_hash=compute_inputs_hash(user_message),
        )

    if session is not None:
        return _build(session)
    with session_scope() as sess:
        return _build(sess)
